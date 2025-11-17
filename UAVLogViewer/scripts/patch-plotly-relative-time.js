const fs = require('fs')
const path = require('path')

const targetFile = path.join(__dirname, '..', 'node_modules', 'plotly.js', 'src', 'plots', 'plots.js')

const relativeTimeBlock = [
    'function relativeTimeFormatter(milliseconds) {',
    "    let outputString = ''",
    '    let seconds = milliseconds / 1000',
    '    let minutes = Math.floor(seconds / 60)',
    '    seconds %= 60',
    '    let hours = Math.floor(minutes / 60)',
    '    minutes %= 60',
    '    let days = Math.floor(hours / 24)',
    '    hours %= 24',
    "    outputString = '' + seconds.toFixed(3).padStart(6, '0')",
    '    if (minutes >= 1 || hours >= 1 || days >= 1) {',
    "        outputString = `${minutes}`.padStart(2, '0') + ':' + outputString",
    '    }',
    '    if (hours >= 1 || days >= 1) {',
    "        outputString = hours + ':' + outputString",
    '    }',
    '    if (days >= 1) {',
    "        outputString = days + ' days ' + outputString",
    '    }',
    '    return outputString',
    '}'
].join('\n')

const oldNumberFormat = `return {\n        numberFormat: function(formatStr) {\n            try {\n                formatStr = formatLocale(formatObj).format(\n                    Lib.adjustFormat(formatStr)\n                );\n            } catch(e) {\n                Lib.warnBadFormat(formatStr);\n                return Lib.noFormat;\n            }\n\n            return formatStr;\n        },`
const newNumberFormat = `return {\n        numberFormat: function(formatStr) {\n            return relativeTimeFormatter;\n        },`

function applyPatch(source) {
    let updated = source
    if (!updated.includes('function relativeTimeFormatter(milliseconds)')) {
        const marker = 'function getFormatter(formatObj, separators) {'
        if (!updated.includes(marker)) {
            throw new Error('Unable to find getFormatter definition inside plotly.js to inject formatter')
        }
        updated = updated.replace(marker, `${relativeTimeBlock}\n\n${marker}`)
    }

    if (!updated.includes(newNumberFormat)) {
        if (!updated.includes(oldNumberFormat)) {
            throw new Error('Unable to locate Plotly numberFormat block to patch')
        }
        updated = updated.replace(oldNumberFormat, newNumberFormat)
    }
    return updated
}

function maybePatchFile() {
    if (!fs.existsSync(targetFile)) {
        console.warn(`[plotly-patch] File not found: ${targetFile}. Skipping relative time patch.`)
        return
    }

    const original = fs.readFileSync(targetFile, 'utf8')
    try {
        const patched = applyPatch(original)
        if (patched === original) {
            console.log('[plotly-patch] Plotly already contains the relative time formatter.')
            return
        }
        fs.writeFileSync(targetFile, patched, 'utf8')
        console.log('[plotly-patch] Applied relative time formatter to Plotly axis labels.')
    } catch (error) {
        console.warn(`[plotly-patch] ${error.message}. Plotly axis ticks will fall back to the default formatter.`)
    }
}

maybePatchFile()
