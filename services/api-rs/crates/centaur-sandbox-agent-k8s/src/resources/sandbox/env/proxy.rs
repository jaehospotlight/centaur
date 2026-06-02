use std::collections::{BTreeMap, BTreeSet};

pub(super) fn proxy_env(
    proxy_host: &str,
    proxy_port: u16,
    api_host: Option<&str>,
    no_proxy_extra: &[String],
) -> BTreeMap<String, String> {
    let proxy_url = format!("http://{proxy_host}:{proxy_port}");
    let no_proxy = no_proxy_value(proxy_host, api_host, no_proxy_extra);
    let ca_cert_path = "/firewall-certs/ca-cert.pem".to_owned();
    BTreeMap::from([
        ("FIREWALL_HOST".to_owned(), proxy_host.to_owned()),
        ("FIREWALL_PROXY_PORT".to_owned(), proxy_port.to_string()),
        ("HTTP_PROXY".to_owned(), proxy_url.clone()),
        ("HTTPS_PROXY".to_owned(), proxy_url.clone()),
        ("http_proxy".to_owned(), proxy_url.clone()),
        ("https_proxy".to_owned(), proxy_url),
        ("NO_PROXY".to_owned(), no_proxy.clone()),
        ("no_proxy".to_owned(), no_proxy),
        ("NODE_EXTRA_CA_CERTS".to_owned(), ca_cert_path.clone()),
        ("REQUESTS_CA_BUNDLE".to_owned(), ca_cert_path.clone()),
        ("CURL_CA_BUNDLE".to_owned(), ca_cert_path.clone()),
        ("SSL_CERT_FILE".to_owned(), ca_cert_path.clone()),
        ("GIT_SSL_CAINFO".to_owned(), ca_cert_path),
    ])
}

fn no_proxy_value(proxy_host: &str, api_host: Option<&str>, extra_values: &[String]) -> String {
    let mut hosts = BTreeSet::from([
        "localhost",
        "127.0.0.1",
        "::1",
        proxy_host,
        "api",
        "victoriametrics",
        "victorialogs",
    ]);
    hosts.extend(api_host.filter(|value| !value.is_empty()));
    for value in extra_values {
        hosts.extend(
            value
                .split(',')
                .map(str::trim)
                .filter(|host| !host.is_empty()),
        );
    }
    hosts.into_iter().collect::<Vec<_>>().join(",")
}
