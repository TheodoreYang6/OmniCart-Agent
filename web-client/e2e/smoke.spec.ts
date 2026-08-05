import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

async function mockGuestIdentity(page: Page) {
  await page.route('**/api/auth/profile', (route) => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ detail: '未登录' }),
  }))
  await page.route('**/api/auth/guest', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ guest_id: 'guest_e2e', guest_token: 'signed', expires_at: '2099-01-01T00:00:00Z' }),
  }))
  await page.route('**/api/cart**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ user_id: 'guest_e2e', items: [], total_price: 0, total_count: 0 }),
  }))
}

test.beforeEach(async ({ page }) => {
  await mockGuestIdentity(page)
  await page.addInitScript(() => localStorage.clear())
})

test('welcome remains usable without horizontal overflow', async ({ page }) => {
  await page.goto('/chat')
  await expect(page.getByRole('textbox', { name: '给欧米发送消息' })).toBeVisible()
  const geometry = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    inputBottom: document.querySelector('textarea')?.getBoundingClientRect().bottom ?? Infinity,
    viewportBottom: window.innerHeight,
  }))
  expect(geometry.overflow).toBe(false)
  expect(geometry.inputBottom).toBeLessThanOrEqual(geometry.viewportBottom)
  const mascot = page.locator('[data-omi-perch]')
  const title = page.getByRole('heading', { name: /嗨，我是欧米/ })
  const [mascotBox, titleBox] = await Promise.all([mascot.boundingBox(), title.boundingBox()])
  expect(mascotBox).not.toBeNull()
  expect(titleBox).not.toBeNull()
  expect(mascotBox!.y + mascotBox!.height).toBeLessThanOrEqual(titleBox!.y + 8)
})

test('profile uses a wide workspace on desktop and folds safely on mobile', async ({ page }) => {
  await page.goto('/profile')
  await expect(page.getByRole('heading', { name: '我的工作台' })).toBeVisible()
  const geometry = await page.evaluate(() => {
    const hero = document.querySelector('.profile-spotlight')?.getBoundingClientRect()
    return {
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      heroWidth: hero?.width ?? 0,
      viewport: window.innerWidth,
    }
  })
  expect(geometry.overflow).toBe(false)
  if (geometry.viewport >= 1280) expect(geometry.heroWidth).toBeGreaterThan(500)
  else expect(geometry.heroWidth).toBeGreaterThan(280)
})

test('login and unknown route expose accessible semantics', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByLabel('用户名')).toHaveAttribute('autocomplete', 'username')
  await expect(page.locator('input[name="password"]')).toHaveAttribute('autocomplete', 'current-password')

  await page.goto('/does-not-exist')
  await expect(page.getByRole('heading', { name: '欧米没找到这个页面' })).toBeVisible()
  await expect(page).toHaveTitle(/页面不存在/)
})

test('chat, login and profile have no serious accessibility violations', async ({ page }) => {
  for (const path of ['/chat', '/login', '/profile']) {
    await page.goto(path)
    const results = await new AxeBuilder({ page }).analyze()
    expect(results.violations.filter((item) => ['serious', 'critical'].includes(item.impact ?? ''))).toEqual([])
  }
})
