# android-ble 
# android ios 鸿蒙 ble 蓝牙程序
#### uniapp demo 在uniappx demo 下的zip 文件
### 插件测试使用方法

1.选择试用，绑定要试用的项目appid，

2.选择后下载到对应的本地项目，

3.按照文档 -》把插件引入项目（即 import {BleLib} from "@/uni_modules/android-ble" 需要先引入），

4.发布-》云打包-》选择制作基座-》打包等基座制作完成

5.运行 -》 运行到手机或模拟器-》运行到Androidapp基座-》选择使用自定义基座运行-》选择手机-》运行

6.之前若安装过基座 ，请卸载之前的基座


### 鸿蒙普通授权版本 不支持 需要购买源码版本

### uniappx
~~~
import {BleLib,MyApiResult,BleScanResult,BleServices,ScanRssiBR} from "@/uni_modules/android-ble"	

var lib=new BleLib()
~~~
### uniapp
~~~
import {BleLib} from "@/uni_modules/android-ble"

var lib=new BleLib()
~~~


### 检测蓝牙是否开启
~~~
var open=lib.isEnabled();// true 为蓝牙开启 false 为关闭
~~~
### 扫描蓝牙时候监听蓝牙信息  
~~~

~~~

### 监听系统蓝牙开关状态
uniappx
~~~
lib.onBtOpenStateListenerj(function(res:MyApiResult){
	
})
~~~
uniapp
~~~
lib.onBtOpenStateListenerj(function(res){
	
})
~~~

### 蓝牙扫描
uniappx
~~~
lib.startScanBleDevice(15000,function(res:MyApiResult){
	if(res.type==0){
		var scan=res.data as BleScanResult;
	}else{
		
	}
})
~~~
uniapp
~~~
lib.startScanBleDevice(15000,function(res){
	if(res.type==0){
		var scan=res.data;
	}else
	
	}
})
~~~

###  蓝牙扫描时监听蓝牙广播信号变化 实时回掉  多次
uniappx
~~~
lib.onScanDataListener(function(res:MyApiResult){
	var data=res.data as ScanRssiBR;
	
})
~~~
uniappx
~~~
lib.onScanDataListener(function(res){
	
})
~~~

### 蓝牙是否连接
~~~
var isconnect=lib.isConnected();
~~~

### 获取已连接设备id
~~~
var device=lib.getConnectMac();// 已经连接返回mac 地址 未连接返回“”
~~~
### 打开Android蓝牙

uniappx
~~~
lib.openBtBluetooth(function(res:MyApiResult){
	
})
~~~
uniapp
~~~
lib.openBtBluetooth(function(res){
	
})
~~~
### 连接蓝牙
### connect
参数1 需要连接的mac 地址

参数2  是否开启蓝牙自动连接 true 自动连接 false 取消自动连接

参数3 连接回掉 type  0  成功  10000 蓝牙连接失败 10001 蓝牙异常断开   

uniappx
~~~
lib.connect(device.device.address,false,function(res:MyApiResult){
	console.log(res)
	// type==0 表示连接成功 type==1 
	if(res.type==0){
		
	}else{
		
	}
})
~~~
uniapp
~~~
lib.connect(device.device.address,false,function(res){
	console.log(res)
	// type==0 表示连接成功 type==1 
	if(res.type==0){
		
	}else{
		
	}
})
~~~

### 自动连接蓝牙（需要先调用connect 方法）
~~~
lib.startAutoConnectBt(6000);
~~~
### 取消自动连接蓝牙
~~~
lib.cancelAutoConnectBt();
~~~

### 扫描蓝牙服务与特征值
### scanServices
连接蓝牙后需要获扫描蓝牙与特征值

uniappx
~~~
lib.scanServices(function(resSevice:MyApiResult){
	
});
~~~
uniapp
~~~
lib.scanServices(function(resSevice){
	
});
~~~	
### 断开蓝牙
~~~
lib.close();
~~~


### 开启服务消息通知
### onNotityReadBleData
参数1 通知服务uuid  

参数2 通知属性 uuid

参数3  true 开启通知读取  false 关闭通知读取

参数4 回掉结果

uniappx
~~~
lib.onNotityReadBleData(lib.getSericUUID(),
	lib.getNotityUUID(),
	true,
	function(res:MyApiResult){
		console.log(res)
	}	
)
~~~
uniapp
~~~
lib.onNotityReadBleData(lib.getSericUUID(),
	lib.getNotityUUID(),
	true,
	function(res){
		console.log(res)
	}	
)
~~~
### 获取自动识别读写服务uuid
~~~
lib.getSericUUID()
~~~
### 获取自动识通知uuid
~~~
lib.getNotityUUID()
~~~
### 获取自动识写入uuid
~~~
lib.getwriteUUID()
~~~
### 发送数据
### writeDataToBle
参数1 服务uuid   

参数2 写入属性uuid

参数3 16进制数组

参数4 写入回掉

uniappx
~~~
var b:number[]=[0x55,0xff,oxAA] as number[];
lib.writeDataToBle(
	lib.getSericUUID(),
	lib.getwriteUUID(),
	b,
	function(res:MyApiResult){
		console.log(res)
	}	
)	
~~~
uniapp
~~~
var b=[0x55,0xff,oxAA] ;
lib.writeDataToBle(
	lib.getSericUUID(),
	lib.getwriteUUID(),
	b,
	function(res){
		console.log(res)
	}	
)	
~~~




### 发送16进制字符数据
### writeStringDataToBle
参数1 服务uuid

参数2 写入属性uuid

参数3  16进制字符串 

参数4 回掉写入结果

uniappx
~~~
var d="00FFAABB"
lib.writeStringDataToBle(
	lib.getSericUUID(),
	lib.getwriteUUID(),
	d,
	function(res:MyApiResult){
		console.log(res)
	}
)
~~~
uniapp
~~~~
var d="00FFAABB"
lib.writeStringDataToBle(
	lib.getSericUUID(),
	lib.getwriteUUID(),
	d,
	function(res){
		console.log(res)
	}
)
~~~~

### 设置mtu(仅安卓)
### setMtu
uniappx
~~~
lib.setMtu(512,function(res:MyApiResult){
	
})
~~~
uniapp
~~~
lib.setMtu(512,function(res){
	
})
~~~


### 读取rssi 信号 需要蓝牙已经连接
 uniapp
~~~
lib.readRssi(function(b){
	console.log(b)
})
~~~
uniappx
~~~
lib.readRssi(function(b:MyApiResult){
	console.log(b)
})
~~~

### 字符转16进制拼接字符
### string2ByteStrWithCharset
参数1 普通文本
 
参数2  传utf-8 gbk
~~~
lib.string2ByteStrWithCharset("测试","gbk")
~~~

### 进制拼接字符转文本
### byte2StringWithCharset
参数1 16进制拼接字符 

参数2  传utf-8 gbk
~~~
lib.string2ByteStrWithCharset("E6B58BE8AF95","utf-8")
~~~

 ### 打赏
感谢您使用此插件，如果你觉得本插件，解决了你的问题，赠人玫瑰，手留余香。





