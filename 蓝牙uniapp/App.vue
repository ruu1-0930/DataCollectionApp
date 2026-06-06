<script>
import { useBlueToothStoreWithOut } from '@/store/modules/blueTooth'

export default {
  onLaunch: function () {
    const blueToothStore = useBlueToothStoreWithOut()

    console.log('App Launch')
    blueToothStore.initBle()
  },
  onShow: function () {
    console.log('App Show')
  },
  onHide: function () {
    console.log('App Hide')
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
