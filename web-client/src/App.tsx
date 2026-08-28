import { Component, lazy, Suspense, useEffect, type ErrorInfo, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { ToastHost } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { useAuthStore } from '@/store/authStore'

const ChatPage = lazy(() => import('@/pages/ChatPage').then((m) => ({ default: m.ChatPage })))
const ShopPage = lazy(() => import('@/pages/ShopPage').then((m) => ({ default: m.ShopPage })))
const ProductDetailPage = lazy(() => import('@/pages/ProductDetailPage').then((m) => ({ default: m.ProductDetailPage })))
const CartPage = lazy(() => import('@/pages/CartPage').then((m) => ({ default: m.CartPage })))
const OrdersPage = lazy(() => import('@/pages/OrdersPage').then((m) => ({ default: m.OrdersPage })))
const ProfilePage = lazy(() => import('@/pages/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const AddressPage = lazy(() => import('@/pages/AddressPage').then((m) => ({ default: m.AddressPage })))
const PreferencePage = lazy(() => import('@/pages/PreferencePage').then((m) => ({ default: m.PreferencePage })))
const LoginPage = lazy(() => import('@/pages/LoginPage').then((m) => ({ default: m.LoginPage })))
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })))
const BrandPreviewPage = import.meta.env.DEV
  ? lazy(() => import('@/pages/BrandPreviewPage').then((m) => ({ default: m.BrandPreviewPage })))
  : null

function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation()
  const initialized = useAuthStore((state) => state.initialized)
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn())
  if (!initialized) return <PageLoader />
  if (!isLoggedIn) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
  }
  return children
}

function PageLoader() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center" role="status" aria-label="页面加载中">
      <Spinner />
    </div>
  )
}

function AppLifecycle() {
  const initialize = useAuthStore((state) => state.initialize)
  const expireSession = useAuthStore((state) => state.expireSession)
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => { void initialize() }, [initialize])
  useEffect(() => {
    const handleUnauthorized = () => {
      expireSession()
      void initialize()
    }
    window.addEventListener('omnicart:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('omnicart:unauthorized', handleUnauthorized)
  }, [expireSession, initialize])
  useEffect(() => {
    const goLogin = () => {
      if (location.pathname !== '/login') navigate('/login', { state: { from: location.pathname } })
    }
    window.addEventListener('omnicart:login-required', goLogin)
    return () => window.removeEventListener('omnicart:login-required', goLogin)
  }, [location.pathname, navigate])
  useEffect(() => {
    const labels: Record<string, string> = {
      '/chat': '与欧米聊天', '/shop': '好物广场', '/cart': '购物车',
      '/orders': '我的订单', '/profile': '个人中心', '/address': '收货地址',
      '/preferences': '购物偏好', '/login': '登录',
    }
    const routeLabel = labels[location.pathname]
      ?? (location.pathname.startsWith('/product/') ? '商品详情' : '页面不存在')
    document.title = `${routeLabel} · 欧米购物智能体`
  }, [location.pathname])
  return null
}

class AppErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('UI error', error, info) }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <main className="aurora-bg flex min-h-screen items-center justify-center p-6">
        <section className="glass max-w-md p-8 text-center" role="alert">
          <h1 className="text-xl font-bold text-ink">页面暂时出了点问题</h1>
          <p className="mt-2 text-sm text-ink-muted">欧米已经记下错误，请刷新后重试。</p>
          <button className="btn-primary mt-5" onClick={() => window.location.reload()}>刷新页面</button>
        </section>
      </main>
    )
  }
}

export default function App() {
  return (
    <AppErrorBoundary>
      <AppLifecycle />
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/shop" element={<ShopPage />} />
            <Route path="/product/:productId" element={<ProductDetailPage />} />
            <Route path="/cart" element={<ProtectedRoute><CartPage /></ProtectedRoute>} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/orders" element={<ProtectedRoute><OrdersPage /></ProtectedRoute>} />
            <Route path="/address" element={<ProtectedRoute><AddressPage /></ProtectedRoute>} />
            <Route path="/preferences" element={<ProtectedRoute><PreferencePage /></ProtectedRoute>} />
            {BrandPreviewPage && <Route path="/brand" element={<BrandPreviewPage />} />}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
      <ToastHost />
    </AppErrorBoundary>
  )
}
