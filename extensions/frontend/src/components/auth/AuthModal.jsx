/* ============================================================
   EXTENSION — components/auth/AuthModal.jsx
   Login / Register modal. Uses useAuth hook.
   Rendered inside ExtensionHub header — no existing UI touched.
   ============================================================ */

import { useState } from "react";
import "./AuthModal.css";

export default function AuthModal({ onClose, auth }) {
  const [mode,     setMode]     = useState("login");   // "login" | "register"
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [name,     setName]     = useState("");
  const [msg,      setMsg]      = useState("");

  const submit = async () => {
    setMsg("");
    if (!email || !password) { setMsg("Email and password required."); return; }
    if (mode === "register" && password.length < 8) { setMsg("Password must be ≥ 8 characters."); return; }

    const result = mode === "login"
      ? await auth.login(email, password)
      : await auth.register(email, password, name);

    if (result.success) {
      onClose();
    } else {
      setMsg(result.error || "Something went wrong.");
    }
  };

  return (
    <div className="am-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="am-modal">
        <button className="am-close" onClick={onClose}>✕</button>

        <div className="am-logo">◈ ValScore Intelligence</div>
        <h2 className="am-title">{mode === "login" ? "Sign In" : "Create Account"}</h2>
        <p className="am-sub">
          {mode === "login"
            ? "Access your wishlist & saved products across devices."
            : "Your wishlist and saved items will be linked to your account."}
        </p>

        <div className="am-tabs">
          <button className={`am-tab ${mode === "login"    ? "am-tab-active" : ""}`} onClick={() => { setMode("login");    setMsg(""); }}>Sign In</button>
          <button className={`am-tab ${mode === "register" ? "am-tab-active" : ""}`} onClick={() => { setMode("register"); setMsg(""); }}>Register</button>
        </div>

        <div className="am-form">
          {mode === "register" && (
            <input className="am-input" placeholder="Display name (optional)" value={name}
              onChange={e => setName(e.target.value)} />
          )}
          <input className="am-input" type="email" placeholder="Email address" value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === "Enter" && submit()} />
          <input className="am-input" type="password" placeholder="Password (min 8 chars)" value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === "Enter" && submit()} />
        </div>

        {msg && <div className="am-error">{msg}</div>}
        {auth.error && !msg && <div className="am-error">{auth.error}</div>}

        <button className="am-submit" onClick={submit} disabled={auth.loading}>
          {auth.loading ? "Please wait…" : mode === "login" ? "Sign In →" : "Create Account →"}
        </button>

        <p className="am-note">
          Session data (saves, wishlist) will be linked to your account automatically.
        </p>
      </div>
    </div>
  );
}
