<template>
  <div class="h-full w-full flex">
    <div class="w-200px flex-shrink-0 flex flex-col justify-start py-20px items-center bg-#112f59 overflow-hidden">
      <div style="border-bottom: 1px solid rgba(255, 255, 255, 0.1)" class="text-#fff text-18px flex w-full flex-col justify-center h-200px items-center pb-20px">
        <img src="../../assets/logo.png" alt="" srcset="" class="w-60px h-60px object-fill rounded-50%" />
        <div class="mt-16px">后台管理</div>
      </div>

      <div class="flex-1 overflow-auto w-full">
        <el-menu unique-opened :default-active="defaultActive">
          <template v-for="item in state.menu" :key="item.index">
            <el-menu-item @click="routerLink(item)" :index="item.index">
              {{ item.text }}
            </el-menu-item>
          </template>
        </el-menu>
      </div>
      <div style="border-top: 1px solid rgba(255, 255, 255, 0.1)" class="pt-16px px-20rpx text-#F6F7F8 mt-16px flex w-full items-center justify-around">
        <!-- 展示账号信息 -->
        <div class="flex items-center gap-10px">
          <img :src="adminStore.admin.avatar ? prefix + adminStore.admin.avatar : defaultAvatar" alt="avatar" class="w-24px h-24px object-cover rounded-50% cursor-pointer border border-#e5e7eb" />
          <div class="flex flex-col max-w-120px">
            <span class="text-14px overflow-hidden text-ellipsis whitespace-nowrap" :title="adminStore.admin.name">{{ adminStore.admin.name }}</span>
            <span class="text-12px overflow-hidden text-ellipsis whitespace-nowrap" :title="adminStore.admin.username">{{ adminStore.admin.username }}</span>
          </div>
        </div>
        <el-tooltip content="loginout">
          <img src="../../assets/images/loginout.png" @click="routerLink({ text: '注销' })" class="w-24px h-24px object-fill rounded-50% cursor-pointer" />
        </el-tooltip>
      </div>
    </div>
    <div class="flex-1 overflow-hidden bg-#f6f7f8 min-w-1080px">
      <RouterView v-slot="{ Component }">
        <Transition name="fade-slide" mode="out-in" appear>
          <KeepAlive>
            <component :is="Component" />
          </KeepAlive>
        </Transition>
      </RouterView>
    </div>
    <el-dialog v-model="state.formVisible" title="修改密码" width="400" :show-close="false">
      <el-input v-model="state.password" type="password" show-password placeholder="请输入您的新密码" class="mt-20px mb-5px" />
      <el-input v-model="state.password1" type="password" show-password placeholder="请再次输入您的新密码" class="mt-20px mb-5px" />
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="state.formVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit">保存</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/useAdminStore'
import { onBeforeMount } from 'vue'
import { ElMessageBox } from 'element-plus'
// import { updateUserApi } from '@/service/api';
import defaultAvatar from '@/assets/logo.png'

const prefix = import.meta.env.MODE === 'development' ? import.meta.env.VITE_BASE_URL : import.meta.env.VITE_BASE_URL_PRO

const defaultActive = computed(() => {
  let index = ''
  state.menu.forEach((item) => {
    if (router.currentRoute.value.name === item.name) index = item.index
  })
  return index
})

const adminStore = useAdminStore()
const router = useRouter()
const state = reactive({
  formVisible: false,
  password: '',
  password1: '',
  menu: [
    // {
    //   text: '仪表盘',
    //   name: 'manager-dashboard',
    //   index: '1'
    // },
    // {
    //   text: '用户',
    //   name: 'manager-user',
    //   index: '2'
    // },
    // {
    //   text: '统计',
    //   name: 'manager-statistics',
    //   index: '3'
    // },
    // {
    //   text: '排程',
    //   name: 'manager-schedule',
    //   index: '4'
    // },
    // {
    //   text: '设置',
    //   name: 'manager-settings',
    //   index: '5'
    // },
    {
      text: '用户数据',
      name: 'manager-user-data',
      index: '6'
    },
    {
      text: '设备数据',
      name: 'manager-device-data',
      index: '7'
    },
    {
      text: '账号管理',
      name: 'manager-account',
      index: '8'
    }
  ]
})

onBeforeMount(async () => {
  if (!adminStore.token) {
    router.push({
      name: 'proxy-login'
    })
  }
})

async function handleSubmit() {
  if (!state.password) return ElMessage.warning('请您的输入密码!')
  if (state.password1 != state.password) return ElMessage.warning('两次密码不相同!')
  await updateUserApi({
    id: adminStore.admin.id,
    password: state.password
  })
  ElMessage.success('密码修改成功!')
  state.formVisible = false
}

function routerLink({ name, text }) {
  if (text === '修改密码') {
    state.formVisible = true
    state.password = ''
    state.password1 = ''
    return
  }

  if (text === '注销') {
    ElMessageBox.confirm('确认退出登录?', '提示', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      logout()
    })
    return
  }
  if (name) {
    router.push({
      name
    })
    return
  }
}

function logout() {
  adminStore.adminLogout()
  router.push({
    name: 'proxy-login'
  })
}
</script>

<style lang="scss">
.el-menu {
  background: #112f59;
  color: #fff;
  width: 100%;
  border-right: none;
}
.el-menu-item,
.el-sub-menu__title {
  color: rgba(255, 255, 255, 0.8);
  height: 44px;
  // justify-content: center;
  &:hover {
    background: #2b5a96;
  }
}
.el-sub-menu .el-menu-item {
  height: 44px;
  padding-left: 30px !important;
}
.el-menu-item.is-active {
  background: #409eff;
  color: #fff !important;
}
</style>
