import DefaultTheme from "vitepress/theme";
import AgentFlightConsole from "./components/AgentFlightConsole.vue";
import HomeFlightTeaser from "./components/HomeFlightTeaser.vue";
import "./custom.css";

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component("AgentFlightConsole", AgentFlightConsole);
    app.component("HomeFlightTeaser", HomeFlightTeaser);
  },
};
