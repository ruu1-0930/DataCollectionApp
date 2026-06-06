<script>
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { usePatientStoreWithOut } from '@/store/modules/patient'

export default {
  onLaunch: function () {
    const blueToothStore = useBlueToothStoreWithOut()
    blueToothStore.initBle()

    const op = useOperatorStoreWithOut()
    const ps = usePatientStoreWithOut()

    // 网关：未启用 → 启用页；已启用未解锁 → 解锁页；已解锁未选患者 → 选患者；否则进首页
    if (!op.isEnabled) {
      uni.reLaunch({ url: '/pages/setup/enable' })
    } else if (!op.unlocked) {
      uni.reLaunch({ url: '/pages/setup/unlock' })
    } else if (!ps.current) {
      uni.reLaunch({ url: '/pages/patient/select' })
    }
    // 已启用+已解锁+有当前患者：留在默认首页
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
