import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#111318",
          raised: "#1a1d25",
          overlay: "#22252f",
        },
        accent: {
          DEFAULT: "#6c8cff",
          dim: "#4a62cc",
          glow: "#8fa8ff",
        },
        edge: {
          prerequisite: "#f0a060",
          causation: "#e0556a",
          dependency: "#d080e0",
          influence: "#50b0d0",
          composition: "#60c080",
          contrast: "#e0c040",
          application: "#9098b0",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      animation: {
        "fade-in": "fadeIn 0.5s ease-out",
        "slide-up": "slideUp 0.5s ease-out",
        "pulse-glow": "pulseGlow 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseGlow: {
          "0%, 100%": { boxShadow: "0 0 8px rgba(108, 140, 255, 0.3)" },
          "50%": { boxShadow: "0 0 20px rgba(108, 140, 255, 0.6)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
