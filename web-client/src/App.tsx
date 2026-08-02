import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { ToastHost } from '@/components/ui/Toast'
import { ChatPage } from '@/pages/ChatPage'
import { ShopPage } from '@/pages/ShopPage'
import { ProductDetailPage } from '@/pages/ProductDetailPage'
import { CartPage } from '@/pages/CartPage'
import { OrdersPage } from '@/pages/OrdersPage'
import { ProfilePage } from '@/pages/ProfilePage'
import { AddressPage } from '@/pages/AddressPage'
import { PreferencePage } from '@/pages/PreferencePage'
import { BrandPreviewPage } from '@/pages/BrandPreviewPage'
import { LoginPage } from '@/pages/LoginPage'

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/shop" element={<ShopPage />} />
          <Route path="/product/:productId" element={<ProductDetailPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/address" element={<AddressPage />} />
          <Route path="/preferences" element={<PreferencePage />} />
          {/* 品牌资产走查页（设计评审用，不参与业务流程） */}
          <Route path="/brand" element={<BrandPreviewPage />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Route>
      </Routes>
      <ToastHost />
    </>
  )
}
