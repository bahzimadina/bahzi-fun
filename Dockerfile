# bahzi.fun — landing page OmniTools (static, di-serve nginx)
# Kontainer dihubungkan ke network `webnet` agar bisa dijangkau web-gateway by Host.
FROM nginx:1.27-alpine

# Konfigurasi nginx: gzip + cache aset + HTML selalu fresh + fallback SPA-friendly
RUN printf 'server {\n\
  listen 80;\n\
  server_name _;\n\
  server_tokens off;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
\n\
  gzip on;\n\
  gzip_types text/plain text/css application/javascript application/json image/svg+xml;\n\
  gzip_min_length 512;\n\
\n\
  location ~* \\.(css|js|svg|png|jpg|jpeg|webp|ico|woff2?)$ {\n\
    expires 7d;\n\
    add_header Cache-Control "public, max-age=604800, immutable";\n\
    try_files $uri =404;\n\
  }\n\
\n\
  location = /index.html {\n\
    add_header Cache-Control "no-cache";\n\
  }\n\
\n\
  location / {\n\
    add_header Cache-Control "no-cache";\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf

COPY index.html /usr/share/nginx/html/index.html
COPY assets/ /usr/share/nginx/html/assets/

# Cache-busting otomatis: ganti penanda __V__ di index.html dengan hash isi aset.
# Setiap kali CSS/JS berubah, hash berubah -> URL aset berubah -> cache Cloudflare/browser tidak basi.
RUN V=$(cat /usr/share/nginx/html/assets/styles.css /usr/share/nginx/html/assets/app.js | md5sum | cut -c1-10) \
    && sed -i "s/__V__/$V/g" /usr/share/nginx/html/index.html \
    && echo "asset version: $V" \
    && grep -o 'assets/[a-z]*\.\(css\|js\)?v=[a-z0-9]*' /usr/share/nginx/html/index.html

EXPOSE 80
