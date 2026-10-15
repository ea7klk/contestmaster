import axe from 'axe-core'

export async function expectAccessible(element: Element) {
  const parent = document.createElement('div')
  parent.append(element)
  document.body.append(parent)
  try {
    const results = await axe.run(parent, {
      runOnly: {
        type: 'tag',
        values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'],
      },
    })
    expect(results.violations.map(({ id, help, nodes }) => ({
      id,
      help,
      targets: nodes.map((node) => node.target),
    }))).toEqual([])
  } finally {
    parent.remove()
  }
}
