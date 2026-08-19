import { defineParameterType } from 'playwright-bdd'

defineParameterType({
  name: 'texte',
  regexp: /\u00ab([^\u00bb]*)\u00bb/,
  transformer: (s: string) => s.trim()
})
