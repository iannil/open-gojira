import { expect, type Page, type Locator } from '@playwright/test';

// Click a custom `.g-tab` (Portfolio/Discipline/Valuation use these instead of antd Tabs).
export async function clickGTab(page: Page, label: string | RegExp): Promise<void> {
  const tab = page.locator('.g-tab, .aw-tab', { hasText: label }).first();
  await tab.waitFor({ state: 'visible' });
  await tab.click();
}

// Antd Select with search: open, type code, pick highlighted option, close.
export async function selectAntdOption(combobox: Locator, code: string): Promise<void> {
  await combobox.click();
  await combobox.locator('input').first().fill(code);
  // dropdown options live in a portal at body level.
  const page = combobox.page();
  const option = page
    .locator('.ant-select-item-option:not(.ant-select-item-option-disabled)')
    .filter({ hasText: code })
    .first();
  await option.waitFor({ state: 'visible', timeout: 10_000 });
  await option.click();
}

// Read a stat-card value from the Dashboard.
export async function readStat(page: Page, label: string | RegExp): Promise<number> {
  const card = page.locator('.stat-card', { hasText: label }).first();
  await card.waitFor();
  const raw = await card.locator('.stat-value').first().innerText();
  return Number(raw.replace(/,/g, '')) || 0;
}

// Wait for the custom toast notification used by AnalysisPage.
export async function expectToast(page: Page, text: string | RegExp): Promise<void> {
  await expect(page.locator('.g-toast').filter({ hasText: text }).first()).toBeVisible({
    timeout: 10_000,
  });
}

// Wait for an antd message (used by most other pages).
export async function expectAntdMessage(page: Page, text: string | RegExp): Promise<void> {
  await expect(
    page.locator('.ant-message-notice').filter({ hasText: text }).first(),
  ).toBeVisible({ timeout: 10_000 });
}
