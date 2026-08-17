<script>
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { resolveLaunchRoute } from '@/utils/appLaunch'

export default {
  onLaunch: function () {
    const blueToothStore = useBlueToothStoreWithOut()
    blueToothStore.initBle()

    const op = useOperatorStoreWithOut()
    const ps = usePatientStoreWithOut()

    const launchRoute = resolveLaunchRoute({
      enabled: op.isEnabled,
      unlocked: op.unlocked,
      hasPatient: !!ps.current,
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
