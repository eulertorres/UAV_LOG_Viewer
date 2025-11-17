const path = require('path')

module.exports = {
    rootDir: path.resolve(__dirname, '../../'),
    moduleFileExtensions: [
        'js',
        'json',
        'vue'
    ],
    moduleNameMapper: {
        '^@/(.*)$': '<rootDir>/src/$1'
    },
    transform: {
        '^.+\\.js$': '<rootDir>/node_modules/babel-jest',
        '.*\\.(vue)$': '<rootDir>/test/unit/vueTransformStub.js'
    },
    testPathIgnorePatterns: [
        '<rootDir>/test/e2e'
    ],
    setupFiles: ['<rootDir>/test/unit/setup'],
    mapCoverage: true,
    coverageDirectory: '<rootDir>/test/unit/coverage',
    collectCoverageFrom: [
        'src/**/*.{js,vue}',
        '!src/main.js',
        '!src/router/index.js',
        '!**/node_modules/**'
    ],
    setupTestFrameworkScriptFile: '<rootDir>/test/unit/jest.setup.js'
}
