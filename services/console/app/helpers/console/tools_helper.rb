module Console::ToolsHelper
  def tool_secret_summary(secret)
    case secret.kind
    when "static"
      if secret.mode == "inject"
        target = secret.inject_header.presence || "?#{secret.inject_query_param}"
        "Inject #{target}"
      else
        targets = Array(secret.match_headers)
        targets << "path" if secret.match_path
        targets << "query" if secret.match_query
        "Replace #{targets.presence&.join(", ") || "placeholder"}"
      end
    when "gcp_auth"
      "GCP OAuth token"
    when "aws_auth"
      "AWS SigV4"
    when "oauth_token"
      "#{secret.grant} OAuth token"
    when "pg_dsn"
      "Postgres DSN #{secret.database}"
    when "hmac"
      "HMAC signer"
    else
      secret.type
    end
  end

  def tool_secret_source_refs(secret)
    refs = secret.source_refs
    return tag.span("none", class: "text-zinc-600") if refs.empty?

    safe_join(refs.map { |ref| tag.code(ref, class: "rounded bg-ink-700 px-1.5 py-0.5 text-xs text-zinc-300") }, " ")
  end
end
