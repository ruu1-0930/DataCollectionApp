<template>
  <div class="p-5px w-full h-full overflow-auto flex flex-col gap-5px">
    <div class="h-60px bg-white pt-15px pl-15px">
      <el-form :inline="true" class="grid grid-cols-8 gap-16px">
        <el-form-item>
          <el-input v-model="formInline.username" placeholder="登录账号" clearable />
        </el-form-item>
        <el-form-item class="col-span-4">
          <el-button type="primary" @click="onSubmit('query')">查询</el-button>
          <el-button @click="onSubmit('reset')">重置</el-button>
        </el-form-item>
      </el-form>
    </div>
    <div style="height: calc(100% - 60px)" class="bg-white p-15px">
      <div id="table-warper" style="height: 100%">
        <div class="h-40px mb-10px" ref="controlsRef">
          <el-form :inline="true" class="grid grid-cols-8 gap-16px">
            <el-form-item class="col-span-4">
              <el-button type="primary" @click="onSubmit('add')">新增</el-button>
              <el-button @click="onSubmit('query')">刷新</el-button>
              <el-button :disabled="!state.select.length" type="danger" @click="onSubmit('delete')">删除选中</el-button>
            </el-form-item>
          </el-form>
        </div>
        <el-table border stripe v-loading="state.loading" :data="state.tableData" :height="state.tabHeight" style="width: 100%" @selection-change="handleSelectionChange">
          <el-table-column type="selection" width="50" />
          <el-table-column type="index" label="序号" width="60" />
          <el-table-column property="username" label="登录账号" min-width="160" />
          <el-table-column property="password" label="登录密码" min-width="140">
            <template #default="{ row }">
              <span>••••••</span>
            </template>
          </el-table-column>
          <el-table-column property="role" label="角色" min-width="120" />
          <el-table-column property="status" label="状态" min-width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === '启用' ? 'success' : 'warning'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="" min-width="1" />
          <el-table-column fixed="right" label="操作" width="160">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="onSubmit('edit', row)">编辑</el-button>
              <el-popconfirm title="是否确认删除?" @confirm="onSubmit('delete_single', row)">
                <template #reference>
                  <el-button type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="state.formVisible" :title="state.formTitle" width="520" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef" class="py-10px" label-position="left">
        <div class="grid grid-cols-1 gap-16px">
          <el-form-item label="登录账号：" prop="username">
            <el-input v-model="form.username" placeholder="请输入登录账号" clearable />
          </el-form-item>
          <el-form-item label="登录密码：" prop="password">
            <el-input v-model="form.password" type="password" show-password placeholder="请输入登录密码" clearable />
          </el-form-item>
          <el-form-item label="角色：" prop="role">
            <el-select v-model="form.role" placeholder="请选择角色" style="width: 100%">
              <el-option label="管理员" value="管理员" />
              <el-option label="普通用户" value="普通用户" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态：" prop="status">
            <el-select v-model="form.status" placeholder="请选择状态" style="width: 100%">
              <el-option label="启用" value="启用" />
              <el-option label="禁用" value="禁用" />
            </el-select>
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="state.formVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit">确认</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, onMounted, ref, nextTick } from 'vue'

const state = reactive({
  tabHeight: 300,
  loading: false,
  tableData: [],
  select: [],
  formVisible: false,
  formTitle: ''
})

const formInline = reactive({
  username: ''
})

onMounted(() => {
  const el = document.getElementById('table-warper')
  if (el) {
    calcTableHeight()
    window.addEventListener('resize', () => {
      calcTableHeight()
    })
  }
  getList()
})

function calcTableHeight() {
  const target = document.getElementById('table-warper')
  if (!target) return
  const controls = controlsRef?.value
  const extra = controls ? controls.getBoundingClientRect().height + 10 : 0
  state.tabHeight = target.getBoundingClientRect().height - extra
}

function getList() {
  state.loading = true
  // 假数据
  setTimeout(() => {
    state.tableData = [
      { id: 1, username: 'admin', password: '123456', role: '管理员', status: '启用' },
      { id: 2, username: 'user01', password: '123456', role: '普通用户', status: '启用' }
    ]
    state.loading = false
  }, 200)
}

function onSubmit(type) {
  if (type === 'query') {
    getList()
  } else if (type === 'reset') {
    formInline.username = ''
    getList()
  } else if (type === 'add') {
    state.formVisible = true
    state.formTitle = '新增账号'
    nextTick(() => {
      formRef.value?.resetFields()
      form.id = ''
      form.username = ''
      form.password = ''
      form.role = '普通用户'
      form.status = '启用'
    })
  } else if (type === 'edit') {
    state.formVisible = true
    state.formTitle = '编辑账号'
    nextTick(() => {
      for (const key in form) {
        form[key] = arguments[1][key]
      }
    })
  } else if (type === 'delete') {
    const ids = state.select.map((i) => i.id)
    state.tableData = state.tableData.filter((i) => !ids.includes(i.id))
  } else if (type === 'delete_single') {
    const row = arguments[1]
    state.tableData = state.tableData.filter((i) => i.id !== row.id)
  }
}

function handleSelectionChange(e) {
  state.select = e
}

const formRef = ref(null)
const controlsRef = ref(null)
const form = reactive({
  id: '',
  username: '',
  password: '',
  role: '普通用户',
  status: '启用'
})
const rules = reactive({
  username: [{ required: true, message: '请输入登录账号!', trigger: 'blur' }],
  password: [{ required: true, message: '请输入登录密码!', trigger: 'blur' }]
})

async function handleSubmit() {
  await formRef.value.validate((valid) => {
    if (!valid) return
    if (!form.id) {
      form.id = Date.now()
      state.tableData.push({ ...form })
    } else {
      state.tableData = state.tableData.map((item) => (item.id === form.id ? { ...item, ...form } : item))
    }
    state.formVisible = false
  })
}
</script>

<style scoped lang="scss">
::v-deep(.el-form-item) {
  margin-bottom: 0 !important;
  margin-right: 0 !important;
}
</style>
