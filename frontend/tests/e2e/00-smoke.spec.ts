import { test, expect } from '@playwright/test';

test.describe('00 启动与冒烟', () => {
  test('后端 /api/health 返回 ok 或 degraded（db 必须 ok）', async ({ request }) => {
    const res = await request.get('/api/health');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(['ok', 'degraded']).toContain(body.status);
    expect(body.checks?.database).toBe('ok');
  });


  test('前端首页加载且导航包含 10 个一级菜单', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.topnav-brand-name')).toHaveText('Gojira');
    const items = page.locator('.topnav-item');
    await expect(items).toHaveCount(10);
    for (const label of ['总览', '自选', '筛选', '对比', '分析', '估值', '财务', '持仓', '纪律', '告警']) {
      await expect(items.filter({ hasText: label }).first()).toBeVisible();
    }
  });
});
