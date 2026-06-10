const fs = require('fs');
const iconv = require('iconv-lite');

function fix() {
    const filePath = 'apps/site/views.py';
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');
    const newLines = [];

    for (let line of lines) {
        if (line.includes('ط') || line.includes('ظ')) {
            try {
                // The characters were mapped from UTF-8 bytes to Windows-1256.
                // We need to get the Windows-1256 bytes of this string, then decode those bytes as UTF-8.
                const buf = iconv.encode(line, 'win1256');
                const fixed = buf.toString('utf8');
                
                // if it decodes properly and doesn't contain replacement character
                if (fixed.includes('\uFFFD')) {
                    newLines.push(line);
                } else {
                    newLines.push(fixed);
                }
            } catch (e) {
                newLines.push(line);
            }
        } else {
            newLines.push(line);
        }
    }

    fs.writeFileSync(filePath, newLines.join('\n'), 'utf8');
    console.log('Fixed file.');
}

fix();
