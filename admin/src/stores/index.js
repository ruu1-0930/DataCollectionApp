import { createPinia } from 'pinia';
import { setupPersistedStatePlugin } from './plugins/persistence';
import { resetSetupStore } from './plugins/reset';

export function setupStore(app) {
    const store = createPinia();
    setupPersistedStatePlugin(store);
    store.use(resetSetupStore);
    app.use(store);
}
