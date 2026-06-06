import { defineConfig, presetAttributify, presetUno, transformerDirectives, presetIcons } from 'unocss';

export default defineConfig({
  transformers: [transformerDirectives()],
  presets: [presetAttributify({}), presetUno(), presetIcons({})],
  rules: [['max-w-content', { width: 'max-content' }]],
});
