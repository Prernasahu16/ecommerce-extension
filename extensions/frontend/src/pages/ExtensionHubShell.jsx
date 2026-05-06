/* ============================================================
   EXTENSION — pages/ExtensionHubShell.jsx
   Wraps ExtensionHub with AuthProvider + header bar.
   This is what App.jsx imports — ExtensionHub.jsx unchanged.
   ============================================================ */

import { useState } from "react";
import ExtensionHub from "./ExtensionHub";
import "./ExtensionHub.css";
import { AuthProvider, _useAuthState } from "../hooks/useAuth";
import AuthModal    from "../components/auth/AuthModal";
import "./ExtensionHubShell.css";

export default function ExtensionHubShell() {
  return (
    <AuthProvider>
      <ShellInner />
    </AuthProvider>
  );
}

function ShellInner() {
  const auth = _useAuthState();
  const [showAuth, setShowAuth] = useState(false);
  const [goWishlist, setGoWishlist] = useState(false);

  return (
    <div className="ehs-root">
      {/* Top bar — auth controls + price drop badge */}
      <div className="ehs-topbar">
        <span className="ehs-brand">◈ Intelligence Hub</span>

        <div className="ehs-topbar-right">
          {/* Price drop badge — lazy loaded to avoid import if no alerts */}
          <PriceDropBadgeLazy onWishlistClick={() => setGoWishlist(true)} />

          {auth.isAuthed ? (
            <div className="ehs-user-pill">
              <span className="ehs-user-name">{auth.user?.display_name || auth.user?.email?.split("@")[0]}</span>
              <button className="ehs-logout-btn" onClick={auth.logout}>Sign out</button>
            </div>
          ) : (
            <button className="ehs-auth-btn" onClick={() => setShowAuth(true)}>
              Sign in / Register
            </button>
          )}
        </div>
      </div>

      {/* Main hub — receives goWishlist flag to auto-switch tab */}
      <ExtensionHub externalTab={goWishlist ? "wishlist" : undefined} onTabChange={() => setGoWishlist(false)} />

      {showAuth && <AuthModal auth={auth} onClose={() => setShowAuth(false)} />}
    </div>
  );
}

function PriceDropBadgeLazy({ onWishlistClick }) {
  // Dynamic import avoids loading polling logic until shell mounts
  const [Badge, setBadge] = useState(null);
  if (!Badge) {
    import("../components/wishlist/PriceDropBadge").then(m => setBadge(() => m.default));
  }
  if (!Badge) return null;
  return <Badge onClick={onWishlistClick} />;
}
