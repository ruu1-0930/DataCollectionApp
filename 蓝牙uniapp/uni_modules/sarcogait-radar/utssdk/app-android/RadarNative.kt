package uts.sdk.modules.sarcogaitRadar

import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import io.dcloud.uts.UTSAndroid
import org.json.JSONObject
import org.json.JSONArray
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.InetAddress
import java.net.URL
import java.io.ByteArrayOutputStream
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** No process-wide network binding: authenticated cloud calls keep their route. */
object RadarNative {
    private val io = Executors.newFixedThreadPool(8)
    private val deadlines = Executors.newSingleThreadScheduledExecutor()
    private val main = Handler(Looper.getMainLooper())
    private class Operation {
        val cancelled = AtomicBoolean(false)
        val timedOut = AtomicBoolean(false)
        @Volatile var close: (() -> Unit)? = null
        fun check() {
            if (cancelled.get()) throw IllegalStateException("cancelled")
            if (timedOut.get()) throw IllegalStateException("timeout")
        }
        fun attach(action: () -> Unit) { close = action; if (cancelled.get() || timedOut.get()) action() }
        fun cancel() { cancelled.set(true); close?.invoke() }
        fun expire() { timedOut.set(true); close?.invoke() }
    }
    private val operations = ConcurrentHashMap<String, Operation>()
    private fun context(): Context = UTSAndroid.getAppContext() ?: throw IllegalStateException("unsupported")
    private fun permission(ctx: Context): String = if (Build.VERSION.SDK_INT >= 37 && ctx.applicationInfo.targetSdkVersion >= 37) "android.permission.ACCESS_LOCAL_NETWORK" else ""
    private fun permitted(ctx: Context): Boolean { val p = permission(ctx); return p.isEmpty() || ctx.checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED }
    private fun capability(): String {
        val ctx = context(); val p = permission(ctx)
        val declared = p.isEmpty() || (ctx.packageManager.getPackageInfo(ctx.packageName, PackageManager.GET_PERMISSIONS).requestedPermissions?.contains(p) == true)
        return JSONObject().put("supported", Build.VERSION.SDK_INT >= 23).put("permitted", Build.VERSION.SDK_INT >= 23 && permitted(ctx))
            .put("sdk", Build.VERSION.SDK_INT).put("targetSdk", ctx.applicationInfo.targetSdkVersion).put("permission", p).put("declared", declared).toString()
    }
    private data class Scope(val network: Network, val address: String, val prefix: Int) {
        fun json(): String = JSONObject().put("networkToken", network.networkHandle.toString()).put("address", address).put("prefixLength", prefix).toString()
    }
    private fun scope(): Scope {
        if (Build.VERSION.SDK_INT < 23) throw IllegalStateException("unsupported")
        val ctx = context()
        if (!permitted(ctx)) throw SecurityException()
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        // Select the real Wi-Fi Network, never the cellular default or a VPN.
        for (network in cm.allNetworks) {
            val cap = cm.getNetworkCapabilities(network) ?: continue
            if (!cap.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) || cap.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) continue
            val link = cm.getLinkProperties(network) ?: continue
            val ip = link.linkAddresses.firstOrNull { it.address is Inet4Address && privateIP(it.address.hostAddress ?: "") } ?: continue
            return Scope(network, ip.address.hostAddress!!, ip.prefixLength)
        }
        throw IllegalStateException("wifi_unavailable")
    }
    private fun privateIP(ip: String): Boolean {
        if (!Regex("(0|[1-9][0-9]{0,2})(\\.(0|[1-9][0-9]{0,2})){3}").matches(ip)) return false
        val p = ip.split('.').map { it.toInt() }
        return p.all { it <= 255 } && (p[0] == 10 || p[0] == 172 && p[1] in 16..31 || p[0] == 192 && p[1] == 168)
    }
    fun cancel(id: String) { operations[id]?.cancel() }
    fun execute(method: String, ip: String, timeoutMs: Int, id: String, callback: (String, String) -> Unit) {
        val operation = Operation()
        if (id.isNotEmpty()) operations.put(id, operation)?.cancel()
        io.execute {
            var value = ""; var code = ""
            val deadline = if (method == "read") deadlines.schedule({ operation.expire() }, timeoutMs.coerceIn(1, 2500).toLong(), java.util.concurrent.TimeUnit.MILLISECONDS) else null
            try {
                operation.check()
                value = when (method) {
                    "capabilities" -> capability()
                    "wifiScope" -> scope().json()
                    "name" -> resolveName(operation)
                    "read" -> read(ip, timeoutMs.coerceIn(1, 2500), operation)
                    else -> throw IllegalStateException("unsupported")
                }
                operation.check()
            } catch (_: SecurityException) { code = "permission" }
            catch (e: Exception) {
                val safe = setOf("unsupported", "wifi_unavailable", "cancelled", "network_changed", "response_too_large", "redirect", "invalid_ip")
                code = if (operation.cancelled.get()) "cancelled"
                    else if (operation.timedOut.get() || e is java.net.SocketTimeoutException) "timeout"
                    else if (safe.contains(e.message)) e.message!! else "network"
            } finally {
                deadline?.cancel(false)
                operation.close?.invoke()
                if (id.isNotEmpty()) operations.remove(id, operation)
            }
            val result = value; val error = code
            main.post { callback(result, error) }
        }
    }
    private fun read(ip: String, timeout: Int, op: Operation): String {
        if (!privateIP(ip)) throw IllegalStateException("invalid_ip")
        val current = scope()
        val connection = current.network.openConnection(URL("http://$ip:80/api/targets")) as HttpURLConnection
        op.attach { connection.disconnect() }
        connection.instanceFollowRedirects = false
        connection.connectTimeout = timeout; connection.readTimeout = timeout
        connection.requestMethod = "GET"; connection.useCaches = false
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("Cookie", "")
        connection.setRequestProperty("Authorization", "")
        // No cloud API client, cookies, Authorization or arbitrary caller headers.
        try {
            op.check()
            val status = connection.responseCode
            if (status in 300..399) throw IllegalStateException("redirect")
            if (status != 200) throw IllegalStateException("network")
            if (connection.contentLength > 32768) throw IllegalStateException("response_too_large")
            val data = ByteArrayOutputStream()
            connection.inputStream.use { input ->
                val buffer = ByteArray(2048)
                while (true) {
                    op.check()
                    val n = input.read(buffer, 0, minOf(buffer.size, 32769 - data.size()))
                    if (n < 0) break
                    data.write(buffer, 0, n)
                    if (data.size() > 32768) throw IllegalStateException("response_too_large")
                }
            }
            if (scope().network != current.network) throw IllegalStateException("network_changed")
            return data.toString("UTF-8")
        } finally { connection.disconnect() }
    }
    // Ask only ld2450.local A with the mDNS QU bit. No DNS-SD service is required.
    private fun resolveName(op: Operation): String {
        val current = scope()
        val wm = context().applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val lock = wm.createMulticastLock("sarcogait-radar-name")
        lock.setReferenceCounted(false)
        val socket = DatagramSocket(null)
        op.attach { socket.close(); if (lock.isHeld) lock.release() }
        try {
            lock.acquire(); socket.bind(java.net.InetSocketAddress(0)); current.network.bindSocket(socket); socket.soTimeout = 500
            val query = byteArrayOf(0,0,0,0,0,1,0,0,0,0,0,0,6,108,100,50,52,53,48,5,108,111,99,97,108,0,0,1,0x80.toByte(),1)
            socket.send(DatagramPacket(query, query.size, InetAddress.getByName("224.0.0.251"), 5353))
            val found = linkedSetOf<String>(); val deadline = android.os.SystemClock.elapsedRealtime() + 500
            while (android.os.SystemClock.elapsedRealtime() < deadline && found.size < 8) {
                op.check(); socket.soTimeout = maxOf(1, (deadline - android.os.SystemClock.elapsedRealtime()).toInt())
                val bytes = ByteArray(2048); val packet = DatagramPacket(bytes, bytes.size)
                try { socket.receive(packet) } catch (_: java.net.SocketTimeoutException) { break }
                found.addAll(parseAnswers(bytes.copyOf(packet.length)))
            }
            if (scope().network != current.network) throw IllegalStateException("network_changed")
            return JSONArray(found.toList()).toString()
        } finally { socket.close(); if (lock.isHeld) lock.release() }
    }
    private fun parseAnswers(bytes: ByteArray): List<String> {
        fun u16(i: Int): Int { if (i < 0 || i + 1 >= bytes.size) throw IllegalArgumentException(); return ((bytes[i].toInt() and 255) shl 8) or (bytes[i + 1].toInt() and 255) }
        fun name(start: Int): Pair<String, Int> {
            val labels = mutableListOf<String>(); var i = start; var end = -1; var hops = 0
            while (++hops < 64) {
                if (i >= bytes.size) throw IllegalArgumentException()
                val n = bytes[i].toInt() and 255
                if (n == 0) return labels.joinToString(".").lowercase() to (if (end < 0) i + 1 else end)
                if (n and 0xc0 == 0xc0) { if (end < 0) end = i + 2; i = u16(i) and 0x3fff; continue }
                if (n > 63 || i + 1 + n > bytes.size) throw IllegalArgumentException()
                labels.add(String(bytes, i + 1, n, Charsets.US_ASCII)); i += n + 1
            }
            throw IllegalArgumentException()
        }
        try {
            if (bytes.size < 12 || u16(2) and 0x8000 == 0) return emptyList()
            var i = 12; repeat(minOf(u16(4), 16)) { i = name(i).second + 4 }
            val found = mutableListOf<String>()
            repeat(minOf(u16(6) + u16(8) + u16(10), 64)) {
                val host = name(i); i = host.second
                val type = u16(i); val clazz = u16(i + 2) and 0x7fff; val length = u16(i + 8); i += 10
                if (i + length > bytes.size) return emptyList()
                if (host.first == "ld2450.local" && type == 1 && clazz == 1 && length == 4) {
                    val ip = (i until i + 4).joinToString(".") { (bytes[it].toInt() and 255).toString() }
                    if (privateIP(ip)) found.add(ip)
                }
                i += length
            }
            return found
        } catch (_: Exception) { return emptyList() }
    }
}
