/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Listing images are hot-linked from many portal CDNs; we render them with plain <img>
  // (no next/image domain allow-list to maintain). See docs/V2_PLAN.md §11.
};

export default nextConfig;
