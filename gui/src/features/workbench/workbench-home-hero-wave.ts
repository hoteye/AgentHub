import { LitElement, css, html, svg } from "lit";
import { customElement, queryAll } from "lit/decorators.js";

type GlowWaveConfig = {
  fill: string;
  rail: string;
  initialTransform: string;
  motionTransform: string;
  reverse: boolean;
  delay: number;
};

type DashWaveConfig = {
  d: string;
  direction: "negative" | "positive";
  gradient: {
    x1: string;
    y1: string;
    x2: string;
    y2: string;
  };
};

type AnimationHandle = {
  rafId: number | null;
  timeoutId: number | null;
  stopped: boolean;
};

const GLOW_WAVES: readonly GlowWaveConfig[] = [
  {
    fill: "M6136.63 1839.58C5083.05 1625.73 4409.33 1775.4 3948.58 1976.32C3506.05 2169.27 3031.24 2571.83 2602.85 2437.03C2463.5 2391.5 2312 2298 2168 2060.5C2118 1982 2081.5 1907 2053 1794.5C2006.5 1629.5 1983 1447.5 1980 1416.5L2084 1418.5C2087 1502.5 2091.5 1652.5 2140 1884C2159.48 1941.65 2186 1997.5 2223 2060C2359.22 2290.1 2478.5 2357.5 2595.39 2404.14C3036.19 2560.33 3513.59 2091.29 3949 1834.29C4400.08 1568.04 5124.73 1341.78 6306 1555.5V1886.5L6218 1861L6136.63 1839.58Z",
    rail: "M6692.5 995.5C5511.08 781.7 4379.85 1262.08 3928.71 1528.42C3493.25 1785.51 3090 2168.5 2653 2297.5C2423 2297.5 2318 2044.91 2278.5 1877C2239 1709.09 2215.5 27 2215.5 27",
    initialTransform: "translate(-4936.5 1068.5) rotate(112.277) scale(2093.23 1808.22)",
    motionTransform: "rotate(112.277) scale(1100 910)",
    reverse: true,
    delay: 0,
  },
  {
    fill: "M6305.5 1886C6238.92 1868.36 6205.92 1854.77 6141.5 1840.5C5578.85 1715.92 5086.02 1711.05 4688 1768.5C4383.8 1812.41 4136.01 1894.6 3948.58 1976.33C3506.05 2169.28 3031.39 2571.3 2603 2436.5C2400.5 2372.78 2250.53 2219.83 2122 1980C2035.5 1827 1986 1460.5 1979.5 1419H1884.5C1924.5 1603.5 1966 1879.5 2086 2045C2273.5 2321 2421.5 2418.17 2610.31 2469.91C3025.99 2583.82 3498.95 2247.49 3948.16 2118.36C4270.77 2032.59 4740.42 1954.65 5320 2012.5C5521.5 2037.5 5736.5 2068.5 5961 2122C6074.5 2155.5 6187.03 2198.97 6305.5 2241.5V1886Z",
    rail: "M6635 1310C6543.5 1281.5 6270 1220 6214 1220C5160.29 1006.07 4481 1346.28 4040.5 1584C3632.5 1741.28 3250.5 2180.5 2665 2344C2495.33 2391.38 2457.04 2144.2 2389.5 2060C2321.96 1975.8 2313.5 1788.5 2313.5 1788.5C2291.5 1720 2278.72 268.698 2263.5 24",
    initialTransform: "translate(-5125.5 1225) rotate(117.537) scale(2451.75 1826.23)",
    motionTransform: "rotate(117.537) scale(1100 910)",
    reverse: true,
    delay: 300,
  },
  {
    fill: "M5968.77 2123.26C5042.86 1909.28 4419.08 1982.95 3948.15 2118.35C3498.95 2247.48 3025.99 2583.83 2610.31 2469.9C2553.78 2454.41 2432.5 2411 2321.5 2319C2253.1 2264.61 2186 2181.5 2134 2111C2011.56 1945 1989.5 1907 1885 1417L1808 1413L1823.5 1694C1843 1752 1924 1986 2148.5 2223C2267.55 2357.27 2363 2427 2489.5 2469C2533.18 2483.5 2573 2493 2617.5 2502C3020.23 2595.56 3492.22 2326.11 3947.73 2260.4C4198.97 2224.16 4602.5 2198 5041.5 2254.5C5455.73 2313.79 5880 2409 6307 2568.5V2242.5C6307 2242.5 6196.14 2200.49 6124.5 2175.5C6037.5 2145.16 5968.77 2123.26 5968.77 2123.26Z",
    rail: "M6564 1618.5C6564 1618.5 6411 1576 6148 1522C5221.97 1307.95 4545.49 1607.56 4074.5 1743C3702.35 1890.71 3261.4 2343.15 2686 2396.5C2520.49 2351.14 2426 2280.5 2387 2177C2348 2073.5 2298.67 1945 2271 1895C2243.33 1845 2173.5 469 2173.5 37.5",
    initialTransform: "translate(-4690 1372) rotate(90.7215) scale(4010.32 2354.13)",
    motionTransform: "rotate(90.7215) scale(1100 910)",
    reverse: true,
    delay: 500,
  },
  {
    fill: "M5825 2412.5C5031.5 2194.5 4429.2 2190.93 3947.71 2260.38C3492.2 2326.09 3020.73 2595.56 2618 2502C2408.5 2457.5 2308 2404.5 2122.5 2193.5C2053 2119.5 1911 1947.5 1821.5 1682.5V1961C1828.06 1983.81 1876 2075 1955 2167.5C2011.81 2234.02 2062.5 2277.5 2122 2322.5C2157.5 2349.35 2256.5 2411 2378 2467C2452.5 2500.5 2539.6 2521.19 2625.23 2535.68C3014.8 2609.45 3485.71 2398.39 3947.31 2402.41C4218.4 2404.76 4720.5 2444.69 5209 2568.5C5607.5 2669.5 6032.5 2821.5 6306 2961.5V2567.5C6306 2567.5 6146.16 2509 6042 2476.5C5946 2446.55 5825 2412.5 5825 2412.5Z",
    rail: "M6483 1894C5684.68 1679.82 4712.72 1804 4138 1894C3682.22 1992.5 3096.78 2523.09 2694 2429.5C2528.13 2390.95 2464.5 2330.5 2401.5 2212C2338.5 2093.5 2299.5 1894 2299.5 1894C2261 1838.67 2230.6 200.7 2179 47.5",
    initialTransform: "translate(-5043 1683) rotate(128.591) scale(3173.53 1742.87)",
    motionTransform: "rotate(128.591) scale(1100 910)",
    reverse: true,
    delay: 700,
  },
  {
    fill: "M6307.5 2961.5C6154.5 2882.5 5894 2779.5 5654 2697C5447 2628 5231.5 2571 5019.5 2524C4588 2425 4184 2403.5 3947.29 2402.43C3485.7 2398.42 3014.79 2609.48 2625.21 2535.7C2579.3 2527.01 2492.57 2512.36 2397 2475C2296.5 2429 2171.27 2365.29 2079.5 2289.5C1956 2187.5 1860 2053 1823.5 1965.5L1824.5 2196C1839.5 2234 1922.5 2316.34 2114 2413C2295.83 2504.78 2521.5 2559.5 2632.67 2568.59C3008.95 2623.19 3479.14 2484.88 3946.87 2544.46C4188.5 2571 4662 2678 5077 2827C5351.72 2925.63 5628 3040.5 5863 3146.5C6036.94 3226.68 6194.5 3297.5 6306.5 3357L6307.5 2961.5Z",
    rail: "M6442 2088C5862.5 1843.5 4600.5 1945.5 4098.5 1990C3596.5 2034.5 3260.5 2336.5 2854.5 2454C2645.71 2456.54 2502.01 2354.48 2433.5 2268C2354.83 2168.7 2314.5 2149 2280.5 1990C2261.47 1901.03 2208.5 125 2183.5 35.5",
    initialTransform: "translate(-5028 1473) rotate(124.493) scale(2788.11 1868.1)",
    motionTransform: "rotate(124.493) scale(1100 910)",
    reverse: true,
    delay: 900,
  },
  {
    fill: "M6306.29 3354.5C6143.5 3271 5891.5 3157.5 5615.79 3037.65C5368.5 2927 5090.5 2828.5 4834.79 2745.65C4477.79 2626.15 4146.65 2569.51 3947.17 2544.1C3479.46 2484.52 3009.5 2620.5 2633 2567.5C2509 2552.5 2299.51 2508.53 2112 2411.5C1868.5 2285.5 1841 2220.5 1823 2195L1822 2386C1845.03 2392.19 2008.5 2471.5 2158 2519.5C2283 2562.5 2396.89 2575.38 2428 2579.5C2489.3 2588.03 2561.09 2593.61 2640.5 2601.5C3003.44 2637.56 3472.7 2564.62 3946.75 2686.13C4060.54 2715.29 4219.5 2763.5 4400.5 2832.5C4663 2937 4926.5 3063.5 5252 3234.5C5396.78 3310.56 5569 3414 5721.5 3514C5952.5 3674 5998.5 3720.5 6139.5 3827.5C6198.63 3872.37 6306.29 3918.65 6306.29 3918.65V3354.5Z",
    rail: "M2138.5 214C2100.52 252.105 2259.41 1960.09 2294 1974C2328.59 1987.91 2404.5 2323.5 2501 2409.5C2597.5 2495.5 2602 2467.5 2766 2499.5C3156.5 2452 3693 2130.5 4155 2155C4690.5 2155 5229.5 2048 5797.5 2219.5C6026.5 2247 6330 2294.5 6545.5 2397.5",
    initialTransform: "translate(-3854 2245.5) rotate(122.42) scale(1876.46 1612.9)",
    motionTransform: "rotate(122.42) scale(1100 910)",
    reverse: false,
    delay: 1400,
  },
  {
    fill: "M5297.34 3257.98C4883 3041.5 4459.97 2818.1 3946.43 2686.49C3472.38 2565 3003.05 2637.52 2640.11 2601.46C2559 2590.5 2372.5 2584.5 2211 2536C2030 2482.5 1859 2398.5 1822 2386L1825 2626.5C1878.65 2627.66 2117.32 2622.56 2331 2624C2462.09 2624.88 2583.77 2631.03 2647.57 2634.35C2997.2 2652.49 3465.3 2645.39 3946.01 2828.52C4204.5 2928 4404 3031 4725 3246C4885.79 3353.7 5045.5 3482.5 5169.5 3597.5C5268 3688.85 5334.5 3766.5 5379 3828L6138.5 3826.5C6138.5 3826.5 5898 3633 5727 3517.5C5556 3402 5297.34 3257.98 5297.34 3257.98Z",
    rail: "M6580.5 2735C6484.31 2681.15 5620 2428.55 5511.5 2396.5C5098.5 2274.5 4658.5 2338 4211 2280C3857.37 2234.17 3174 2444.5 2756.5 2517C2586.05 2546.6 2527.37 2354.18 2410.5 2252C2208.94 2075.77 2007.38 253.288 2074 279",
    initialTransform: "translate(-4017 2296) rotate(116.785) scale(2105.98 2084.72)",
    motionTransform: "rotate(116.785) scale(1100 910)",
    reverse: true,
    delay: 1900,
  },
  {
    fill: "M5377 3825.32C5151 3510.5 4473.5 3018 3946.01 2828.52C3465.3 2645.4 2997.19 2652.49 2647.56 2634.35C2581.51 2630.92 2453.5 2624 2317 2623.5C2107 2623 1877.44 2626.2 1825 2626.5V2733C1899.1 2723.21 2040.01 2713.08 2218 2696C2306.19 2686.43 2402.01 2674.97 2506 2670C2603.06 2665.36 2707.5 2665.69 2812.5 2671C2961.08 2678.51 3115.83 2699.09 3268.5 2732.5C3506.41 2784.56 3740.28 2866.58 3945.5 2969.5C4479 3238 4801.84 3610.59 4961.64 3825.32H5377Z",
    rail: "M-0.5 3076C58.1191 3058.86 1998.4 2876.53 2223.7 2855.87C2372.54 2828.14 2487.84 2804.85 2548.91 2807.99C2891.96 2824.62 3150.9 2728.36 3652.99 2776.74C3978.71 2776.74 4411.98 2766.16 4739.74 2807.99C4921.35 2831.16 5018.47 2855.87 5229.08 2855.87C5350.4 2855.87 6188.18 3006.29 6309.5 3033.5",
    initialTransform: "translate(-3715.5 2623) rotate(115.165) scale(1610.9 1696.41)",
    motionTransform: "rotate(115.165) scale(1100 910)",
    reverse: false,
    delay: 2200,
  },
] as const;

const DASH_WAVES: readonly DashWaveConfig[] = [
  {
    d: "M1825 2626C1877.38 2627.13 2146.04 2621.02 2378 2623.5C2514.85 2624.96 2638.6 2633.39 2698.5 2636.5C3035 2653 3483.97 2651.77 3946.5 2828C4252.5 2946.5 4446.5 3062.5 4656.5 3199.5C4788.78 3288.1 4922.9 3382.34 5080 3516.5C5144.14 3571.27 5174.73 3601.25 5235.5 3661.5C5294 3719.5 5327.5 3758.5 5376.5 3825.5",
    direction: "negative",
    gradient: { x1: "4259.43", y1: "1996.41", x2: "4259.43", y2: "2652.17" },
  },
  {
    d: "M3946.66 2685.9C4354.37 2796.62 4648.5 2925.5 5016 3112.5C5102.95 3158 5201.55 3203.75 5297.74 3257.6C5645 3452 5832 3576.5 6138.5 3825.5M3946.64 2685.92C3472.53 2564.39 3003.15 2636.93 2640.16 2600.86C2472.86 2584.24 2406.14 2583.85 2260.73 2548.84C2085.81 2506.73 1829 2388 1829 2388",
    direction: "positive",
    gradient: { x1: "4270.69", y1: "1965.91", x2: "4270.69", y2: "2647.57" },
  },
  {
    d: "M1824.5 2197 C1848 2231 1853 2236 1866 2249.5 C1879 2263 1989 2369.5 2260.45 2476.3 C2419.68 2531.5 2465.94 2542.76 2632.72 2566.97 C3009.05 2621.59 3479.32 2483.23 3947.08 2542.83 C4450.17 2606.92 4922.7 2758.39 5465.61 2972.82",
    direction: "negative",
    gradient: { x1: "4170.74", y1: "1492.82", x2: "4129.61", y2: "3370.72" },
  },
  {
    d: "M1825.5 1971.5C1865 2055.5 1905.33 2112.38 1975.5 2189C2069.26 2291.39 2115.7 2322.62 2260.18 2405.75C2391.29 2481.17 2458.99 2503.56 2625.28 2535.05C3014.9 2608.85 3485.87 2397.72 3947.52 2401.73C4439.84 2406.02 4962.88 2475.72 5633.5 2690.03C5757.5 2730.35 6067.5 2841.8 6315.5 2965",
    direction: "negative",
    gradient: { x1: "4270.69", y1: "1830.5", x2: "4257.5", y2: "2921.5" },
  },
  {
    d: "M5801.36 2406.29C5003.06 2192.09 4429.51 2190.2 3947.94 2259.67C3492.38 2325.4 3020.59 2595.76 2617.81 2502.17C2451.94 2463.62 2378.26 2437.41 2259.88 2334.21C2141.5 2231 2003.5 2049 2003.5 2049C1965 1993.67 1875.1 1844.7 1823.5 1691.5",
    direction: "positive",
    gradient: { x1: "4270.69", y1: "1965.91", x2: "4270.69", y2: "2647.57" },
  },
  {
    d: "M6306.5 2242C6106.5 2167.2 5998.32 2131.17 5969.23 2122.51V2122.49C5043.21 1908.44 4419.35 1982.13 3948.36 2117.57C3499.1 2246.75 3026.09 2583.22 2610.35 2469.25C2444.84 2423.89 2330.29 2333.14 2259.59 2262.67C2188.89 2192.21 2084.17 2046 2056.5 1996C2028.83 1946 1965 1850.5 1887.5 1420.5",
    direction: "positive",
    gradient: { x1: "4270.69", y1: "1965.91", x2: "4270.69", y2: "2647.57" },
  },
  {
    d: "M6307 1886.5C6215.5 1858 6156.07 1842.48 6137.1 1838.72C5083.39 1624.8 4409.6 1774.52 3948.78 1975.51C3506.2 2168.53 3031.33 2571.23 2602.89 2436.38C2437.66 2384.37 2326.83 2275.33 2259.29 2191.13C2191.75 2106.93 2111 1960.5 2111 1960.5C2085.83 1912 2010.9 1693.8 1980.5 1419",
    direction: "positive",
    gradient: { x1: "4270.69", y1: "1965.91", x2: "4270.69", y2: "2647.57" },
  },
  {
    d: "M6305 1554.93C5123.59 1341.13 4400.35 1567.08 3949.21 1833.42C3513.75 2090.51 3036.29 2559.71 2595.44 2403.47C2430.35 2344.96 2323.36 2217.51 2259 2119.59C2194.64 2021.67 2156.5 1927 2156.5 1927C2135 1874.5 2088.5 1665 2084.5 1419",
    direction: "positive",
    gradient: { x1: "4270.69", y1: "1965.91", x2: "4270.69", y2: "2647.57" },
  },
] as const;

const GLOW_STOPS = [
  { offset: "0.12", color: "#FFE88E" },
  { offset: "0.36", color: "#FB9CE5" },
  { offset: "0.72", color: "#096FFF" },
  { offset: "1", color: "#011C42", opacity: "0" },
] as const;

@customElement("workbench-home-hero-wave")
export class WorkbenchHomeHeroWave extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      height: 100%;
      pointer-events: none;
    }

    .wave-shell {
      position: relative;
      width: 100%;
      height: 100%;
      overflow: hidden;
      border-radius: inherit;
    }

    .base-glow {
      position: absolute;
      inset: -6% -8% 24% -8%;
      background:
        radial-gradient(circle at 52% 38%, rgba(9, 111, 255, 0.3), transparent 34%),
        radial-gradient(circle at 40% 26%, rgba(255, 232, 142, 0.22), transparent 22%),
        radial-gradient(circle at 56% 36%, rgba(251, 156, 229, 0.24), transparent 30%);
      filter: blur(28px);
      opacity: 0.95;
    }

    svg {
      position: absolute;
      left: 50%;
      top: 54%;
      width: max(1680px, 132%);
      height: auto;
      transform: translate(-50%, -50%) scale(1.02);
      transform-origin: center;
      mix-blend-mode: screen;
      opacity: 0.88;
    }

    .dash {
      fill: none;
      stroke-width: 6;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-dasharray: 12 12;
      opacity: 0.72;
    }

    .dash-negative {
      animation: dash-negative 1s linear infinite;
    }

    .dash-positive {
      animation: dash-positive 1s linear infinite;
    }

    .vignette {
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at 50% 46%, transparent 24%, rgba(2, 8, 14, 0.12) 58%, rgba(2, 8, 14, 0.54) 100%),
        linear-gradient(180deg, rgba(2, 8, 14, 0.32), rgba(2, 8, 14, 0) 28%, rgba(2, 8, 14, 0.08) 64%, rgba(2, 8, 14, 0.52) 100%);
    }

    .rim-light {
      position: absolute;
      left: 15%;
      right: 15%;
      bottom: -12%;
      height: 42%;
      border-radius: 999px;
      background: radial-gradient(circle at 50% 0%, rgba(108, 190, 255, 0.16), transparent 66%);
      filter: blur(24px);
    }

    @keyframes dash-negative {
      from {
        stroke-dashoffset: 0;
      }

      to {
        stroke-dashoffset: -24;
      }
    }

    @keyframes dash-positive {
      from {
        stroke-dashoffset: 0;
      }

      to {
        stroke-dashoffset: 24;
      }
    }

    @media (max-width: 1200px) {
      svg {
        top: 58%;
        width: max(1460px, 170%);
      }
    }

    @media (max-width: 720px) {
      svg {
        left: 53%;
        top: 60%;
        width: max(1260px, 220%);
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .dash-negative,
      .dash-positive {
        animation: none;
      }
    }
  `;

  private readonly idPrefix = `workbench-wave-${Math.random().toString(36).slice(2, 9)}`;
  private readonly animationHandles: AnimationHandle[] = [];

  @queryAll("[data-wave-rail]")
  private readonly railElements!: NodeListOf<SVGPathElement>;

  @queryAll("[data-wave-glow]")
  private readonly glowElements!: NodeListOf<SVGElement>;

  firstUpdated(): void {
    const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (prefersReducedMotion) {
      return;
    }
    this.startAnimations();
  }

  disconnectedCallback(): void {
    this.stopAnimations();
    super.disconnectedCallback();
  }

  render() {
    const clipId = `${this.idPrefix}-clip`;
    return html`
      <div class="wave-shell" aria-hidden="true">
        <div class="base-glow"></div>
        <svg viewBox="0 0 6635 3825" fill="none" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
          <g clip-path=${`url(#${clipId})`}>
            ${GLOW_WAVES.map(
              (wave, index) => svg`
                <path d=${wave.fill} fill=${`url(#${this.radialGradientId(index)})`}></path>
              `,
            )}
            ${DASH_WAVES.map(
              (wave, index) => svg`
                <path
                  class=${`dash ${wave.direction === "negative" ? "dash-negative" : "dash-positive"}`}
                  d=${wave.d}
                  stroke=${`url(#${this.lineGradientId(index)})`}
                  stroke-miterlimit="10"
                ></path>
              `,
            )}
            ${GLOW_WAVES.map(
              (wave) => svg`
                <path data-wave-rail d=${wave.rail} fill="none" stroke="transparent" stroke-width="1"></path>
              `,
            )}
          </g>
          <defs>
            ${GLOW_WAVES.map(
              (wave, index) => svg`
                <radialGradient
                  id=${this.radialGradientId(index)}
                  data-wave-glow
                  cx="0"
                  cy="0"
                  r="1"
                  gradientUnits="userSpaceOnUse"
                  gradientTransform=${wave.initialTransform}
                >
                  ${GLOW_STOPS.map(
                    (stop) => svg`
                      <stop offset=${stop.offset} stop-color=${stop.color} stop-opacity=${stop.opacity ?? "1"}></stop>
                    `,
                  )}
                </radialGradient>
              `,
            )}
            ${DASH_WAVES.map(
              (wave, index) => svg`
                <linearGradient
                  id=${this.lineGradientId(index)}
                  x1=${wave.gradient.x1}
                  y1=${wave.gradient.y1}
                  x2=${wave.gradient.x2}
                  y2=${wave.gradient.y2}
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#011C42"></stop>
                  <stop offset="0.34" stop-color="#65C2FF"></stop>
                  <stop offset="0.66" stop-color="#A0A0FF" stop-opacity="0.85"></stop>
                  <stop offset="1" stop-color="#096FFF" stop-opacity="0"></stop>
                </linearGradient>
              `,
            )}
            <clipPath id=${clipId}>
              <rect width="6635" height="3825" fill="white"></rect>
            </clipPath>
          </defs>
        </svg>
        <div class="vignette"></div>
        <div class="rim-light"></div>
      </div>
    `;
  }

  private startAnimations() {
    this.stopAnimations();
    GLOW_WAVES.forEach((wave, index) => {
      const rail = this.railElements.item(index);
      const glow = this.glowElements.item(index);
      if (!rail || !glow) {
        return;
      }
      if (typeof rail.getTotalLength !== "function" || typeof rail.getPointAtLength !== "function") {
        return;
      }
      this.startRailAnimation(rail, glow, wave);
    });
  }

  private stopAnimations() {
    for (const handle of this.animationHandles) {
      handle.stopped = true;
      if (handle.timeoutId !== null) {
        clearTimeout(handle.timeoutId);
      }
      if (handle.rafId !== null) {
        cancelAnimationFrame(handle.rafId);
      }
    }
    this.animationHandles.length = 0;
  }

  private startRailAnimation(rail: SVGPathElement, glow: SVGElement, wave: GlowWaveConfig) {
    const totalLength = rail.getTotalLength();
    if (!Number.isFinite(totalLength) || totalLength <= 0) {
      return;
    }

    const handle: AnimationHandle = {
      rafId: null,
      timeoutId: null,
      stopped: false,
    };

    let progress = 0;
    let previousTime: number | null = null;

    const step = (time: number) => {
      if (handle.stopped || !this.isConnected) {
        return;
      }

      if (previousTime === null) {
        previousTime = time;
      }

      const delta = time - previousTime;
      previousTime = time;
      const point = rail.getPointAtLength(progress * totalLength);
      glow.setAttribute("gradientTransform", `translate(${point.x} ${point.y}) ${wave.motionTransform}`);
      progress += (wave.reverse ? -1 : 1) * 0.0001 * delta;

      if (progress > 1) {
        progress -= 1;
      }
      if (progress < 0) {
        progress += 1;
      }

      handle.rafId = requestAnimationFrame(step);
    };

    handle.timeoutId = window.setTimeout(() => {
      if (handle.stopped) {
        return;
      }
      handle.rafId = requestAnimationFrame(step);
    }, wave.delay);

    this.animationHandles.push(handle);
  }

  private radialGradientId(index: number) {
    return `${this.idPrefix}-radial-${index}`;
  }

  private lineGradientId(index: number) {
    return `${this.idPrefix}-line-${index}`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "workbench-home-hero-wave": WorkbenchHomeHeroWave;
  }
}
