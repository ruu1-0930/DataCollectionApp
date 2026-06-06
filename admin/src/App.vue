<template>
    <RouterView v-slot="{ Component }" class="h-full flex justify-center" style="max-width: 1000px;margin: 0 auto;">
        <Transition name="fade-slide" mode="out-in" appear>
            <!-- <KeepAlive> -->
            <component :is="Component" />
            <!-- </KeepAlive> -->
        </Transition>
    </RouterView>
</template>

<script setup></script>

<style lang="scss" scoped></style>
