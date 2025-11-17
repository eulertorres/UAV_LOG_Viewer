const path = require('path')

module.exports = {
    process (src, filename) {
        const componentName = path.basename(filename).replace(/\W+/g, '_')
        return {
            code: `module.exports = {\n  __esModule: true,\n  render () {},\n  staticRenderFns: [],\n  name: '${componentName}'\n}`
        }
    },
    getCacheKey () {
        return 'vue-transform-stub'
    }
}
