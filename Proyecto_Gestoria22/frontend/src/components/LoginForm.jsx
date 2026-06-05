import { useState } from 'react';
import { useAuth } from '../AuthContext';
import Grainient from '../components/Grainient';
import { Shield, Mail, Lock, Eye, EyeOff, AlertCircle } from 'lucide-react';

export default function LoginForm() {
  const [email, setEmail]             = useState('');
  const [password, setPassword]       = useState('');
  const [showPassword, setShowPass]   = useState(false);
  const [isRegistering, setIsReg]     = useState(false);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState('');
  const { login } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    const endpoint = isRegistering ? 'register' : 'login';

    try {
      const response = await fetch(`http://localhost:8000/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json();

      if (response.ok) {
        if (isRegistering) {
          setIsReg(false);
          setError('');
        } else {
          login(data.access_token);
        }
      } else {
        setError(data.detail || 'Correo o contraseña incorrectos.');
      }
    } catch {
      setError('No se pudo conectar con el servidor. Asegúrate de que el backend esté activo.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.root}>

      {/* ── Fondo animado ── */}
      <div style={styles.bg}>
        <Grainient
          color1="#0125aa"
          color2="#f7f9ff"
          color3="#00135e"
          timeSpeed={2.5}
          colorBalance={0.32}
          warpStrength={1.4}
          warpFrequency={11}
          warpSpeed={1.3}
          warpAmplitude={25}
          blendAngle={-12}
          blendSoftness={0.52}
          rotationAmount={800}
          noiseScale={0.15}
          grainAmount={0.07}
          grainScale={0.7}
          grainAnimated={false}
          contrast={1.5}
          gamma={1.25}
          saturation={0.7}
          centerX={0.0}
          centerY={0.0}
          zoom={0.9}
        />
      </div>

      {/* ── Overlay suave para legibilidad ── */}
      <div style={styles.overlay} />

      {/* ── Card central ── */}
      <div style={styles.card}>

        {/* Logo */}
        <div style={styles.logoRow}>
          <div style={styles.logoIcon}>
            <Shield size={22} color="#ffffff" strokeWidth={2.2} />
          </div>
          <div>
            <p style={styles.logoTitle}>GESTIO</p>
            <p style={styles.logoSub}>Compliance Control</p>
          </div>
        </div>

        <div style={styles.divider} />

        {/* Encabezado */}
        <h1 style={styles.heading}>
          {isRegistering ? 'Crear cuenta' : 'Bienvenido'}
        </h1>
        <p style={styles.subheading}>
          {isRegistering
            ? 'Completa tus datos para registrarte en el sistema.'
            : 'Inicia sesión para acceder.'}
        </p>

        {/* Formulario */}
        <form onSubmit={handleSubmit} style={styles.form}>

          {/* Email */}
          <div style={styles.fieldWrap}>
            <label style={styles.label}>Correo electrónico</label>
            <div style={styles.inputWrap}>
              <Mail size={15} color="#adb6c5" style={styles.inputIcon} />
              <input
                type="email"
                required
                placeholder="correo@empresa.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                style={styles.input}
                onFocus={e => e.target.style.borderColor = '#011ba0'}
                onBlur={e => e.target.style.borderColor = '#eef1f8'}
              />
            </div>
          </div>

          {/* Contraseña */}
          <div style={styles.fieldWrap}>
            <label style={styles.label}>Contraseña</label>
            <div style={styles.inputWrap}>
              <Lock size={15} color="#adb6c5" style={styles.inputIcon} />
              <input
                type={showPassword ? 'text' : 'password'}
                required
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                style={{ ...styles.input, paddingRight: 40 }}
                onFocus={e => e.target.style.borderColor = '#012ba0'}
                onBlur={e => e.target.style.borderColor = '#eef1f8'}
              />
              <button
                type="button"
                onClick={() => setShowPass(v => !v)}
                style={styles.eyeBtn}
                tabIndex={-1}
              >
                {showPassword
                  ? <EyeOff size={16} color="#adb6c5" />
                  : <Eye size={16} color="#adb6c5" />}
              </button>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={styles.errorBox}>
              <AlertCircle size={14} color="#dc2626" />
              <span>{error}</span>
            </div>
          )}

          {/* Botón principal */}
          <button
            type="submit"
            disabled={loading}
            style={{
              ...styles.submitBtn,
              opacity: loading ? 0.7 : 1,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
            onMouseEnter={e => !loading && (e.target.style.background = '#0005a1')}
            onMouseLeave={e => e.target.style.background = '#0109a0'}
          >
            {loading ? 'Procesando...' : isRegistering ? 'Crear cuenta' : 'Iniciar sesión'}
          </button>

        </form>

        {/* Toggle registro */}
        <p style={styles.toggleText}>
          {isRegistering ? '¿Ya tienes cuenta?' : '¿No tienes cuenta?'}{' '}
          <button
            onClick={() => { setIsReg(v => !v); setError(''); }}
            style={styles.toggleBtn}
          >
            {isRegistering ? 'Inicia sesión' : 'Regístrate aquí'}
          </button>
        </p>

      </div>
    </div>
  );
}

// ── Estilos ──────────────────────────────────────────────────────
const styles = {
  root: {
    position: 'fixed',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: "'DM Sans', sans-serif",
  },
  bg: {
    position: 'absolute',
    inset: 0,
    zIndex: 0,
  },
  overlay: {
    position: 'absolute',
    inset: 0,
    background: 'rgba(24, 97, 255, 0.18)',
    zIndex: 1,
  },
  card: {
    position: 'relative',
    zIndex: 2,
    width: '100%',
    maxWidth: 580,
    margin: '0 16px',
    background: 'rgba(255, 255, 255, 0.87)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    borderRadius: 15,
    padding: '80px 70px 80px',
    boxShadow: '0 8px 40px rgba(255, 255, 255, 0.18), 0 1px 0 rgba(255,255,255,0.6) inset',
    border: '1px solid rgb(0, 22, 131)',
    animation: 'loginFadeUp 0.5s cubic-bezier(.22,.68,0,1.2) both',
  },
  logoRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 15,
    marginBottom: 30,
  },
  logoIcon: {
    width: 50,
    height: 50,
    borderRadius: 11,
    background: '#001a8d',
    border: '1px solid #00126e',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  logoTitle: {
    margin: 0,
    fontSize: 23,
    fontWeight: 900,
    color: '#0a2a22',
    letterSpacing: '-0.01em',
    fontFamily: "'DM Sans', sans-serif",
  },
  logoSub: {
    margin: '0 0 0',
    fontSize: 15,
    color: '#0a1f94',
    fontWeight: 500,
  },
  divider: {
    height: 1,
    background: 'linear-gradient(90deg, #869ae5, #99aaec)',
    marginBottom: 25,
    borderRadius: 99,
  },
  heading: {
    margin: '0 0 6px',
    fontSize: 30,
    fontWeight: 700,
    color: '#0a132a',
    letterSpacing: '-0.03em',
    fontFamily: "'DM Sans', sans-serif",
  },
  subheading: {
    margin: '0 0 30px',
    fontSize: 14,
    color: '#383f4e',
    fontWeight: 500,
    lineHeight: 1.5,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 18,
  },
  fieldWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  label: {
    fontSize: 13,
    fontWeight: 600,
    color: '#445597',
    letterSpacing: '0.0em',
  },
  inputWrap: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
  },
  inputIcon: {
    position: 'absolute',
    left: 12,
    pointerEvents: 'none',
  },
  input: {
    width: '100%',
    padding: '10px 12px 10px 36px',
    fontSize: 14,
    color: '#0b1836',
    background: '#fcfcff',
    border: '1.5px solid #d3def4e4',
    borderRadius: 9,
    outline: 'none',
    boxSizing: 'border-box',
    transition: 'border-color 0.15s',
    fontFamily: "'DM Sans', sans-serif",
  },
  eyeBtn: {
    position: 'absolute',
    right: 10,
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    padding: 4,
  },
  errorBox: {
    display: 'flex',
    alignItems: 'center',
    gap: 7,
    padding: '9px 12px',
    background: '#fef2f2',
    border: '1px solid #fecaca',
    borderRadius: 9,
    fontSize: 13,
    color: '#dc2626',
  },
  submitBtn: {
    marginTop: 20,
    padding: '13px 14px',
    background: '#002077',
    color: '#fff',
    border: 'none',
    borderRadius: 10,
    fontSize: 15,
    fontWeight: 700,
    letterSpacing: '0.01em',
    transition: 'background 0.15s',
    fontFamily: "'DM Sans', sans-serif",
  },
  toggleText: {
    marginTop: 30,
    textAlign: 'center',
    fontSize: 14,
    color: '#6f7b91',
  },
  toggleBtn: {
    background: 'none',
    border: 'none',
    color: '#6c7fdc',
    fontWeight: 600,
    cursor: 'pointer',
    fontSize: 14,
    fontFamily: "'DM Sans', sans-serif",
    textDecoration: 'underline',
    textUnderlineOffset: 2,
  },
};
