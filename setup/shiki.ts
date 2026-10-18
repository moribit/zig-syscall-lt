import { defineShikiSetup } from '@slidev/types'

// Dark code blocks use brighter variants of the prose reference colors.
export default defineShikiSetup(() => ({
  themes: { light: 'github-dark', dark: 'github-dark' },
  transformers: [{
    name: 'explanation-colors',
    span(node) {
      const value = node.children.map(child => child.type === 'text' ? child.value : '').join('').trim()
      const lang = this.options.lang
      if (!['zig', 'js', 'javascript', 'sh', 'c'].includes(lang ?? '')) return
      if (value.startsWith('//')) {
        node.properties.style = 'color: #a8b5ca'
        return
      }
      let role: string | undefined
      if (/^(io|fd|0|1|2)$/.test(value)) role = 'fd'
      else if (/^(buf|"hello|hello|"hello\\n"|"hello\\n|url|urlA|urlB)$/.test(value)) role = 'buffer'
      else if (/^(n|6|length|future|task|response|text|ra|rb|a|b)$/.test(value)) role = 'result'
      else if (/^(read|write|async|concurrent|await|cancel|fetch|fetchLength|EAGAIN)$/.test(value)) role = 'operation'
      if (role) {
        this.addClassToHast(node, `ref-${role}`)
        // Inline colors from Shiki have higher specificity than stylesheets.
        const palette = { fd: '#8bb9ff', buffer: '#7ee0cc', result: '#d8b4fe', operation: '#ffc078' }
        node.properties.style = `color: ${palette[role as keyof typeof palette]}`
      }
    },
  }],
}))
