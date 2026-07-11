import type { Config } from "tailwindcss";

// Scoped to the admin dashboard (Sprint 4) only. `preflight` is disabled on
// purpose: the rest of the app (styles/globals.css) already ships its own
// reset (`* { box-sizing: border-box; margin: 0; padding: 0 }` etc.) — a
// second, different reset layered on top would risk visually changing pages
// that were never touched by this sprint. Utility classes generated here
// only apply where an admin component actually uses them.
const config: Config = {
  darkMode: "class",
  content: ["./app/admin/**/*.{ts,tsx}", "./components/admin/**/*.{ts,tsx}"],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--admin-border))",
        input: "hsl(var(--admin-input))",
        ring: "hsl(var(--admin-ring))",
        background: "hsl(var(--admin-background))",
        foreground: "hsl(var(--admin-foreground))",
        primary: {
          DEFAULT: "hsl(var(--admin-primary))",
          foreground: "hsl(var(--admin-primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--admin-secondary))",
          foreground: "hsl(var(--admin-secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--admin-muted))",
          foreground: "hsl(var(--admin-muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--admin-accent))",
          foreground: "hsl(var(--admin-accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--admin-card))",
          foreground: "hsl(var(--admin-card-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--admin-success))",
          foreground: "hsl(var(--admin-success-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--admin-destructive))",
          foreground: "hsl(var(--admin-destructive-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--admin-warning))",
          foreground: "hsl(var(--admin-warning-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--admin-radius)",
        md: "calc(var(--admin-radius) - 2px)",
        sm: "calc(var(--admin-radius) - 4px)",
      },
      fontFamily: {
        sans: [
          "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Inter", "Roboto",
          "Helvetica Neue", "Arial", "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
        "slide-up": "slide-up 0.25s ease-out",
        "pulse-slow": "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
