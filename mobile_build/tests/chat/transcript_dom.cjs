// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

// Disposable browser verification of synthetic transcript updates; no network.
const fs = require('fs');
const assert = require('assert/strict');
const {chromium} = require('playwright');

(async () => {
    const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
    const browser = await chromium.launch({headless: true,
        ...(process.env.LOGISTICS_CHROME ? {executablePath: process.env.LOGISTICS_CHROME} : {})});
    try {
        const page = await browser.newPage();
        await page.route('**/*', route => route.abort());
        await page.setContent(fixture.html);
        await page.evaluate(fixture.scripts[0]);
        await page.evaluate(() => {
            const content = document.querySelector('article').chatContent;
            window.originalBlock = content.firstChild;
            window.originalCopy = document.querySelector('.copy');
            window.removedBlocks = 0;
            new MutationObserver(records => {
                for (const record of records) removedBlocks += record.removedNodes.length;
            }).observe(content, {childList: true});
            const range = document.createRange();
            range.selectNodeContents(originalBlock);
            getSelection().addRange(range);
        });
        for (const script of fixture.scripts.slice(1)) {
            await page.evaluate(script);
            const result = await page.evaluate(() => ({
                block: originalBlock === document.querySelector('article').chatContent.firstChild,
                copy: originalCopy === document.querySelector('.copy'),
                selection: getSelection().toString(), removed: removedBlocks,
            }));
            assert(result.block && result.copy);
            assert.equal(result.selection, 'Stable paragraph.');
        }
        const result = await page.evaluate(() => ({removed: removedBlocks,
            html: document.querySelector('article').chatContent.innerHTML}));
        assert.equal(result.html, fixture.expected);
        assert(result.removed <= 3);
        const articleAppearance = () => page.evaluate(() => {
            const article = document.querySelector('article');
            return {
                border: getComputedStyle(article).borderTopWidth,
                radius: getComputedStyle(article).borderTopLeftRadius,
                role: getComputedStyle(article.querySelector('.role')).position,
                copy: getComputedStyle(originalCopy).borderTopWidth,
                sameBlock: originalBlock === article.chatContent.firstChild,
                selection: getSelection().toString(),
                contrast: document.documentElement.classList.contains('logistics-chat-eink'),
            };
        });
        const regular = await articleAppearance();
        assert.equal(regular.role, 'absolute');
        assert.equal(regular.border, '1px');
        await page.evaluate(fixture.contrast_on);
        assert.deepEqual(await articleAppearance(), {
            border: '0px', radius: '0px', role: 'static', copy: '1px', sameBlock: true,
            selection: 'Stable paragraph.', contrast: true,
        });
        await page.evaluate(fixture.contrast_off);
        assert.deepEqual(await articleAppearance(), regular);
        console.log(JSON.stringify({updates: fixture.scripts.length, removed_blocks: result.removed}));
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
