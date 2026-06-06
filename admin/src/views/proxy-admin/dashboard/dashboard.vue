<template>
    <div class="p-5px w-full h-full overflow-hidden flex flex-col gap-5px">
        <Header>
            <el-input v-model="input2" style="width: 340px" size="large" placeholder="Search something" :prefix-icon="Search" />
        </Header>

        <div class="flex flex-1 bg-white p-20px gap-20px">
            <div class="w-40% h-full">
                <div class="h-60% w-full shadow-md rounded-8px p-20px flex flex-col gap-20px">
                    <div class="text-16px font-bold">Health diagnosis</div>
                    <div class="flex items-center justify-between gap-30px flex-1">
                        <img src="@/assets/images/renti.jfif" class="w-20%" />
                        <div class="grid grid-rows-3 grid-cols-2 gap-10px flex-1 h-full">
                            <div class="flex flex-col items-center rounded-8px shadow-md justify-center" v-for="item in HealthData" :key="item.title">
                                <!-- <img src="@/assets/logo.png" class="w-40% rounded-50%" /> -->
                                <!-- <div class="text-16px font-bold"> -->
                                <div class="text-16px font-bold">{{ item.title }}</div>
                                <div class="text-40px font-bold text-#9EC675">{{ item.value }}</div>
                                <!-- </div> -->
                            </div>
                        </div>
                    </div>
                </div>
                <div class="h-40% w-full shadow-md rounded-8px p-20px flex flex-col gap-20px">
                    <div class="text-16px font-bold">Chronich condition</div>
                    <div class="flex-1">
                        <Chronich />
                    </div>
                </div>
            </div>
            <div class="w-60% h-full">
                <div class="h-60% w-full shadow-md rounded-8px p-20px flex flex-col gap-20px">
                    <div class="text-16px font-bold">Calender</div>
                    <div class="flex-1 flex flex-col gap-10px">
                        <div class="grid grid-cols-7 gap-10px">
                            <div
                                class="flex flex-col items-center justify-center cursor-pointer"
                                :class="{ active: dayActive === index }"
                                v-for="(day, index) in days"
                                :key="day.day"
                                @click="dayActive = index"
                            >
                                <div class="text-16px">{{ day.day }}</div>
                                <div class="text-16px font-bold">{{ day.date }}</div>
                            </div>
                        </div>
                        <div class="grid grid-rows-3 gap-10px flex-1">
                            <div class="flex items-center justify-between gap-20px h-100%">
                                <div>
                                    <div class="text-16px font-bold">8:00-8:35</div>
                                    <div class="text-12px text-#999 text-center">AM</div>
                                </div>
                                <div class="flex-1 bg-#CFF1D9 rounded-8px py-14px px-30px flex items-center gap-30px">
                                    <!-- <img src="@/assets/logo.png" class="w-40px h-40px object-fill rounded-50%" /> -->
                                    <div class="flex-1">
                                        <div class="text-16px font-bold">Dentist</div>
                                        <div class="flex justify-between mt-5px">
                                            <span class="text-14px text-#999">Dr. sinta Jojo</span>
                                            <span class="text-14px text-#999">Hospital</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="flex items-center justify-between gap-20px h-100%">
                                <div>
                                    <div class="text-16px font-bold">9:00 -9:30</div>
                                    <div class="text-12px text-#999 text-center">AM</div>
                                </div>
                                <div class="flex-1 bg-#F8DCDF rounded-8px py-14px px-30px flex items-center gap-30px">
                                    <!-- <img src="@/assets/logo.png" class="w-40px h-40px object-fill rounded-50%" /> -->
                                    <div class="flex-1">
                                        <div class="text-16px font-bold">Lungs</div>
                                        <div class="flex justify-between mt-5px">
                                            <span class="text-14px text-#999">Dr. Pawpaw</span>
                                            <span class="text-14px text-#999">Home</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="flex items-center justify-between gap-20px h-100%">
                                <div>
                                    <div class="text-16px font-bold">9:30-9:40</div>
                                    <div class="text-12px text-#999 text-center">AM</div>
                                </div>
                                <div class="flex-1 bg-#F3C538 rounded-8px py-14px px-30px flex items-center gap-30px">
                                    <!-- <img src="@/assets/logo.png" class="w-40px h-40px object-fill rounded-50%" /> -->
                                    <div class="flex-1">
                                        <div class="text-16px font-bold">Bones check</div>
                                        <div class="flex justify-between mt-5px">
                                            <span class="text-14px text-#999">Dr. sarah siahh</span>
                                            <span class="text-14px text-#999">Home</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="h-40% w-full flex gap-20px">
                    <div class="w-50% h-full shadow-md rounded-8px p-20px flex flex-col gap-20px">
                        <div class="text-16px font-bold">Your activity</div>
                        <div class="flex-1">
                            <Activity />
                        </div>
                    </div>
                    <div class="w-50% h-full shadow-md rounded-8px p-20px flex flex-col gap-20px">
                        <div class="text-16px font-bold">Transformed Data</div>

                        <div class="flex-1">
                            <Blood />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, onActivated, onDeactivated } from 'vue';
import { getLatestDataApi } from '@/service/api';
import { Search } from '@element-plus/icons-vue';
import Blood from './components/Blood.vue';
import Chronich from './components/Chronich.vue';
import Activity from './components/Activity.vue';

const input2 = ref('');

const days = ref([
    {
        day: 'Mon',
        date: 1,
    },
    {
        day: 'Tue',
        date: 2,
    },
    {
        day: 'Wed',
        date: 3,
    },
    {
        day: 'Thu',
        date: 4,
    },
    {
        day: 'Fri',
        date: 5,
    },
    {
        day: 'Sat',
        date: 6,
    },
    {
        day: 'Sun',
        date: 7,
    },
]);
const dayActive = ref(0);
const timer = ref(null);

const HealthData = ref([
    {
        title: 'ax',
        value: 0,
    },
    {
        title: 'ay',
        value: 0,
    },
    {
        title: 'az',
        value: 0,
    },
    {
        title: 'gx',
        value: 0,
    },
    {
        title: 'gy',
        value: 0,
    },
    {
        title: 'gz',
        value: 0,
    },
]);

onActivated(() => {
    getLatestData();
    timer.value = setInterval(() => {
        getLatestData();
    }, 10000);
});

const getLatestData = () => {
    getLatestDataApi({}).then(res => {
        if (res.raw_data) {
            HealthData.value.forEach(item => {
                item.value = res.raw_data[item.title] || 0;
            });
        }
    });
};
onDeactivated(() => {
    clearInterval(timer.value);
});
</script>

<style lang="scss" scoped>
.active {
    background-color: #f9ba06;
    border-radius: 10px;
    color: #fff;
}
</style>
