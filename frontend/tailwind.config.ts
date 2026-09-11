import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 色阶：按「相关条数」着色（比原始条数更能反映有效产能）
        heat: {
          0: "#1e293b",
          1: "#0c4a6e",
          2: "#0369a1",
          3: "#0284c7",
          4: "#38bdf8",
        },
      },
    },
  },
  plugins: [],
};

export default config;
