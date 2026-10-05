/** Public address of the site, used for canonical, sitemap and link-preview URLs. */
export const SITE_URL: string = (
  process.env.SITE_URL ?? "https://apexrep.xyz"
).replace(/\/+$/, "");
