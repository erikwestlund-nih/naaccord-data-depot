import Alpine from 'alpinejs'
import collapse from '@alpinejs/collapse'
import Quill from 'quill'
import 'quill/dist/quill.snow.css'

import '../css/app.css';

// Import components
import './components/fileUpload';

Alpine.plugin(collapse)

window.Alpine = Alpine
window.Quill = Quill

Alpine.start()
