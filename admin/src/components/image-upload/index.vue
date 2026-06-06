<template>
    <el-upload :headers="headers" ref="upload" :action="actions" accept="image/*" :limit="9" :show-file-list="false" :on-success="uploadSucess">
        <template #trigger>
            <div class="grid grid-cols-4 gap-16px">
                <div @click.stop class="w-60px h-60px relative" v-for="item in urlList" :key="item">
                    <img :src="item" width="60px" height="60px" />
                    <div
                        @click="deleteImage(item)"
                        class="absolute top-0 right-0 w-16px h-16px bg-#f13131 rounded-full flex items-center justify-center text-white text-2xl"
                    >
                        -
                    </div>
                </div>
                <div
                    v-if="multiple ? urlList.length < 9 : urlList.length === 0"
                    class="w-60px h-60px bg-gray-200 rounded-md flex items-center justify-center text-2xl"
                >
                    +
                </div>
            </div>
        </template>
    </el-upload>
</template>

<script setup>
import { computed } from 'vue';
import { useAdminStore } from '@/stores/useAdminStore';

const adminStore = useAdminStore();
const headers = { Authorization: adminStore.token };
const actions = import.meta.env.MODE === 'development' ? import.meta.env.VITE_BASE_FILE_URL : import.meta.env.VITE_BASE_FILE_URL_PRO;

const props = defineProps({
    multiple: {
        type: Boolean,
        default: false,
    },
    url: {
        type: String,
        default: '',
    },
});

const urlList = computed(() => {
    if (props.multiple) {
        return props.url ? props.url.split(',') : [];
    }
    return props.url ? [props.url] : [];
});

const emit = defineEmits(['update:url']);

const deleteImage = url => {
    const newUrlList = urlList.value.filter(item => item !== url);
    emit('update:url', newUrlList.join(','));
};

const uploadSucess = res => {
    if (props.multiple) {
        urlList.value.push(res.data.path);
        emit('update:url', urlList.value.join(','));
    } else {
        emit('update:url', res.data.path);
    }
};
</script>
