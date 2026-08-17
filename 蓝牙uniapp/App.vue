<script>
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { prepareAppLaunch } from '@/utils/appLaunch'
import { clearToken } from '@/utils/auth'

export default {
  onLaunch: function () {
    const blueToothStore = useBlueToothStoreWithOut()
    blueToothStore.initBle()

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
  onShow() {}, onHide() {}
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
