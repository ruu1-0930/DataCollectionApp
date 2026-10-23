<script>
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'
import { useRadarStoreWithOut } from '@/store/modules/radar'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { prepareAppLaunch } from '@/utils/appLaunch'
import { clearToken } from '@/utils/auth'

export default {
  onLaunch: function () {
    const blueToothStore = useBlueToothStoreWithOut()
    blueToothStore.initBle()
    blueToothStore.ensureCollection()

    const op = useOperatorStoreWithOut()
    const ps = usePatientStoreWithOut()

    const launchRoute = prepareAppLaunch({
      enabled: op.isEnabled,
      unlocked: op.unlocked,
      hasPatient: !!ps.current,
      clearToken,
    })
    if (launchRoute) uni.reLaunch({ url: launchRoute })
  },
  onShow() { useRadarStoreWithOut().setForeground(true) },
  onHide() {
    const ble = useBlueToothStoreWithOut()
    if (ble.collectionState.active) ble.stopCollection('background')
    useRadarStoreWithOut().setForeground(false)
  }
}
</script>

<style lang="scss">
@import './static/css/base.css';
@import './static/iconfont/iconfont.css';
/*每个页面公共css */

.primary-color {
  color: $uni-color-primary;
}
</style>
