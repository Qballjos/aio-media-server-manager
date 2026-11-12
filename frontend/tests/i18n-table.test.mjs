import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { parse as parseJavaScript } from '@babel/parser'
import { parse as parseVue, compileTemplate } from '@vue/compiler-sfc'
import { baseCompile } from '@intlify/message-compiler'
import { BREAKPOINTS, WIDGETS } from '../src/homeGrid.js'
import { SETTINGS_GROUPS } from '../src/settingsNavigation.js'
import { TABLE } from '../src/i18n/locales/table.js'

const sourceRoot = new URL('../src/', import.meta.url)

function visit(node, callback) {
  if (!node || typeof node !== 'object') return
  callback(node)
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach((child) => visit(child, callback))
    else if (value && typeof value === 'object') visit(value, callback)
  }
}

async function sourceFiles(directory, extensions = /\.(js|vue)$/) {
  const files = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(files.map((file) => {
    const url = new URL(file.name + (file.isDirectory() ? '/' : ''), directory)
    return file.isDirectory() ? sourceFiles(url, extensions) : extensions.test(file.name) ? [url] : []
  }))
  return nested.flat()
}

test('translation table has no duplicate source keys', async () => {
  const source = await readFile(new URL('../src/i18n/locales/table.js', import.meta.url), 'utf8')
  const ast = parseJavaScript(source, { sourceType: 'module' })
  const properties = ast.program.body[0].declaration.declarations[0].init.properties
  const seen = new Set()
  for (const property of properties) {
    const key = property.key.value
    assert.ok(!seen.has(key), `Duplicate translation: ${key}`)
    seen.add(key)
  }
})

test('every locale has a valid translation and the same placeholders', () => {
  for (const [key, values] of Object.entries(TABLE)) {
    assert.equal(values.length, 3, key)
    const placeholders = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort()
    const expected = placeholders(key)
    for (const value of [key, ...values]) {
      assert.equal(typeof value, 'string', key)
      assert.ok(value.trim(), key)
      assert.deepEqual(placeholders(value), expected, `${key} -> ${value}`)
      const errors = []
      baseCompile(value, { onError: (error) => errors.push(error.message) })
      assert.deepEqual(errors, [], `${key} -> ${value}`)
    }
  }
})

test('all static translation calls have entries in every locale', async () => {
  const missing = new Set()
  for (const file of await sourceFiles(sourceRoot)) {
    const source = await readFile(file, 'utf8')
    let scripts = [source]
    if (file.pathname.endsWith('.vue')) {
      const { descriptor } = parseVue(source)
      scripts = [descriptor.script?.content, descriptor.scriptSetup?.content].filter(Boolean)
      if (descriptor.template) {
        const compiled = compileTemplate({ source: descriptor.template.content, filename: fileURLToPath(file), id: file.pathname })
        assert.deepEqual(compiled.errors, [], file.pathname)
        scripts.push(compiled.code)
      }
    }
    for (const script of scripts) {
      let ast
      try {
        ast = parseJavaScript(script, { sourceType: 'module' })
      } catch (error) {
        throw new Error(`${file.pathname}: ${error.message}`, { cause: error })
      }
      visit(ast, (node) => {
        if (node.type !== 'CallExpression') return
        const callee = node.callee
        const name = callee.type === 'Identifier' ? callee.name : callee.type === 'MemberExpression' ? callee.property.name : ''
        if (!['t', '$t'].includes(name)) return
        const argument = node.arguments[0]
        function checkArgument(value) {
          if (!value) return
          if (value.type === 'StringLiteral') {
            if (!Object.hasOwn(TABLE, value.value)) missing.add(value.value)
          } else if (value.type === 'TemplateLiteral' && !value.expressions.length) {
            const key = value.quasis[0].value.cooked
            if (!Object.hasOwn(TABLE, key)) missing.add(key)
          } else if (value.type === 'ConditionalExpression') {
            checkArgument(value.consequent)
            checkArgument(value.alternate)
          } else if (value.type === 'LogicalExpression') {
            checkArgument(value.left)
            checkArgument(value.right)
          } else if (value.type === 'MemberExpression' && value.object.type === 'ObjectExpression') {
            value.object.properties.forEach((property) => checkArgument(property.value))
          }
        }
        checkArgument(argument)
      })
    }
  }
  assert.deepEqual([...missing].sort(), [], 'Missing translation source keys')
})

test('shared dynamic navigation and widget labels have translations', () => {
  const keys = [
    ...Object.values(BREAKPOINTS).map((item) => item.label),
    ...Object.values(WIDGETS).flatMap((item) => [item.label, ...item.presets.map((preset) => preset[2])]),
    ...SETTINGS_GROUPS.flatMap((group) => [group.label, ...group.items.flatMap((item) => [item.label, item.description])]),
  ]
  for (const key of keys) assert.ok(Object.hasOwn(TABLE, key), `Missing dynamic translation: ${key}`)
})

// These maps feed t(label) after a lookup, so their values cannot be found by
// inspecting translation call arguments alone.
test('dynamic status and wizard label maps have translations', async () => {
  const sources = [
    ['HomepagePanel.vue', new Set(['STATUS_LABELS', 'STUCK_STATUSES', 'MEDIA_LABELS'])],
    ['WizardPanel.vue', new Set(['TITLE'])],
    ['CatalogView.vue', new Set(['CATEGORY_LABELS'])],
  ]
  for (const [filename, names] of sources) {
    const { descriptor } = parseVue(await readFile(new URL(filename, sourceRoot), 'utf8'))
    const ast = parseJavaScript(descriptor.scriptSetup.content, { sourceType: 'module' })
    const found = new Set()
    visit(ast, (node) => {
      if (node.type !== 'VariableDeclarator' || !names.has(node.id.name)) return
      found.add(node.id.name)
      assert.equal(node.init.type, 'ObjectExpression', node.id.name)
      for (const property of node.init.properties) {
        assert.equal(property.value.type, 'StringLiteral', node.id.name)
        assert.ok(Object.hasOwn(TABLE, property.value.value), `Missing ${node.id.name} translation: ${property.value.value}`)
      }
    })
    assert.deepEqual(found, names, `${filename}: update the translation audit if a label map moves`)
  }
})

test('catalog application descriptions have translations', async () => {
  const directory = new URL('../../applications/', import.meta.url)
  let count = 0
  for (const file of await sourceFiles(directory, /\.py$/)) {
    const source = await readFile(file, 'utf8')
    // AppManifest descriptions are Python string literals. Parse their shared
    // JavaScript string syntax without importing adapters or starting any apps.
    for (const match of source.matchAll(/\bdescription\s*=\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g)) {
      const value = parseJavaScript(`(${match[1]})`).program.body[0].expression.value
      assert.equal(typeof value, 'string', file.pathname)
      assert.ok(Object.hasOwn(TABLE, value), `Missing app description: ${value}`)
      count++
    }
  }
  assert.ok(count > 0, 'Expected to audit application manifest descriptions')
})
