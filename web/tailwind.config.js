// Frappe design (ADR-0013): frappe-ui's preset gives the tokens (surface, ink, outline), type scale and icons.
import preset, { content } from 'frappe-ui/tailwind'

export default {
  presets: [preset],
  content: [...content, './index.html', './src/**/*.{vue,js}'],
}
