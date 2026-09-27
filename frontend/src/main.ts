import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.config.errorHandler = (err, _instance, info) => {
  console.error('[AutoDiagnose] unhandled UI error', info, err)
}
app.mount('#app')
