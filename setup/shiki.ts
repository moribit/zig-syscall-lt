import { defineShikiSetup } from '@slidev/types'

const colors = { fd: '#8bb9ff', buffer: '#7ee0cc', result: '#d8b4fe', operation: '#ffc078' }
function role(value: string): keyof typeof colors {
  if (/^(io|fd|fd5|fds|epfd|pipe|0|1|2|5)$/.test(value)) return 'fd'
  if (value.startsWith('"Hello') || /^(buffer|buf|event|events|url|"hello\\n")$/.test(value)) return 'buffer'
  if (/^(n|count|cqe|42|3000|6|14|128|future|response|text|res|revents)$/.test(value)) return 'result'
  return 'operation'
}

export default defineShikiSetup(() => ({
  themes: { light: 'github-dark', dark: 'github-dark' },
  transformers: [{
    name: 'explanation-colors',
    line(node) {
      // Work on whole lines so split TextMate tokens (shell output, escapes)
      // still receive the same semantic hue as their explanation labels.
      const text = node.children.map((child: any) => child.children?.map((c: any) => c.value ?? '').join('') ?? child.value ?? '').join('')
      const comment = text.indexOf('//')
      const ranges = [...text.matchAll(/"Hello, World!\\n"|"hello\\n"|\b(?:io|fd|fd5|fds|epfd|pipe|buffer|buf|event|events|url|n|count|cqe|42|3000|6|14|128|0|1|2|5|future|response|text|res|revents|async|await|cancel|read|writev|write|poll|epoll_ctl|epoll_wait|epoll_create1|submit|copy_cqe|EAGAIN)\b/g)]
        .filter(match => comment < 0 || match.index! < comment)
        .map(match => ({ start: match.index!, end: match.index! + match[0].length, color: colors[role(match[0])] }))
      let offset = 0
      const output: any[] = []
      for (const child of node.children as any[]) {
        const content = child.children?.map((c: any) => c.value ?? '').join('') ?? child.value ?? ''
        const start = offset
        offset += content.length
        const boundaries = new Set([start, offset])
        for (const range of ranges) {
          if (range.start > start && range.start < offset) boundaries.add(range.start)
          if (range.end > start && range.end < offset) boundaries.add(range.end)
        }
        if (comment >= start && comment < offset) boundaries.add(comment)
        const points = [...boundaries].sort((a, b) => a - b)
        for (let i = 0; i < points.length - 1; i++) {
          const from = points[i], to = points[i + 1]
          const range = ranges.find(r => from >= r.start && to <= r.end)
          const properties = { ...child.properties }
          if (comment >= 0 && from >= comment) properties.style = 'color: #a8b5ca'
          else if (range) properties.style = `color: ${range.color}`
          output.push({ type: 'element', tagName: 'span', properties, children: [{ type: 'text', value: content.slice(from - start, to - start) }] })
        }
      }
      node.children = output
    },
  }],
}))
