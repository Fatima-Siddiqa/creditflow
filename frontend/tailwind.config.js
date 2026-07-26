/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Muted derivatives of the CreditFlow logo (deep indigo / orange
        // swirl / sky-blue waves) -- softened for extended UI use per
        // request, not the poster-bright originals.
        brand: {
          50: "#EEEDFB", 100: "#D9D6F5", 200: "#B3ADEB", 300: "#8D84E0",
          400: "#675BD6", 500: "#4A3FB8", 600: "#3B3294", 700: "#2C2670",
          800: "#1E1A4D", 900: "#100E29",
        },
        accent: {
          50: "#FDF3EC", 100: "#FAE3D1", 200: "#F4C7A3", 300: "#EEAB75",
          400: "#E8934F", 500: "#D67B36", 600: "#B0632A", 700: "#894E22",
          800: "#623819", 900: "#3B2210",
        },
        sky: {
          50: "#EEF7FC", 100: "#D3ECF8", 200: "#A7D9F1", 300: "#7CC5E9",
          400: "#57AEDA", 500: "#3F93BE", 600: "#337699", 700: "#275973",
          800: "#1A3C4D", 900: "#0D1E26",
        },
      },
    },
  },
  plugins: [],
};