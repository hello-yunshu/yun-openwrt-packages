include $(TOPDIR)/rules.mk

PKG_NAME:=nginx-quic
PKG_VERSION:=1.30.7
PKG_RELEASE:=1

PKG_SOURCE:=nginx-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://nginx.org/download/
PKG_HASH:=2565b5c837050e958f70fb0f73c48e2bca4542ad349fd356f46fb0c72610bc6e

PKG_MAINTAINER:=YunWrt <hello-yunshu@users.noreply.github.com>
PKG_LICENSE:=BSD-2-Clause
PKG_LICENSE_FILES:=LICENSE

PKG_BUILD_DIR:=$(BUILD_DIR)/nginx-$(PKG_VERSION)
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

define Package/nginx-quic
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=nginx with HTTP/3 (QUIC) support
  URL:=https://nginx.org/
  DEPENDS:=+libopenssl +libpcre2 +zlib +libpthread
  PROVIDES:=nginx-ssl
  CONFLICTS:=nginx-ssl nginx-full
endef

define Package/nginx-quic/description
  nginx web server compiled with --with-http_v3_module for HTTP/3
  over QUIC. Drop-in replacement for OpenWrt's nginx-ssl package.
  Automatically tracks the latest nginx stable release.
endef

# Cross-compilation: point nginx's custom configure at the OpenWrt SDK
# toolchain and staging dir so OpenSSL, PCRE2, and zlib are found.
NGINX_CONF_ARGS := \
	--prefix=/usr \
	--conf-path=/etc/nginx/nginx.conf \
	--error-log-path=/var/log/nginx/error.log \
	--http-log-path=/var/log/nginx/access.log \
	--pid-path=/var/run/nginx.pid \
	--lock-path=/var/lock/nginx.lock \
	--user=root \
	--group=root \
	--with-cc="$(TARGET_CC)" \
	--with-cc-opt="$(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -I$(STAGING_DIR)/usr/include" \
	--with-ld-opt="$(TARGET_LDFLAGS) -L$(STAGING_DIR)/usr/lib" \
	--with-http_ssl_module \
	--with-http_v2_module \
	--with-http_v3_module \
	--with-http_realip_module \
	--with-http_gzip_static_module \
	--with-http_stub_status_module \
	--with-stream \
	--with-stream_ssl_module \
	--with-stream_quic_module \
	--with-threads \
	--with-pcre2 \
	--with-compat

define Build/Configure
	(cd $(PKG_BUILD_DIR); \
		./configure $(NGINX_CONF_ARGS); \
	)
endef

define Build/Compile
	+$(MAKE) $(PKG_JOBS) -C $(PKG_BUILD_DIR)
endef

define Package/nginx-quic/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/objs/nginx $(1)/usr/sbin/nginx
endef

$(eval $(call BuildPackage,nginx-quic))
