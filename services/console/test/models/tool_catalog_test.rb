require "test_helper"
require "fileutils"
require "tmpdir"

class ToolCatalogTest < ActiveSupport::TestCase
  test "reads tool manifests and parses required and optional secrets" do
    Dir.mktmpdir do |root|
      tool_dir = File.join(root, "research", "demo")
      FileUtils.mkdir_p(tool_dir)
      File.write(
        File.join(tool_dir, "pyproject.toml"),
        <<~TOML
          [project]
          description = "Demo tool"

          [tool.centaur]
          hosts = ["api.example.com"]
          secrets = [
            { type = "http", name = "DEMO_API_KEY", mode = "inject", inject_header = "Authorization", inject_formatter = "Bearer {{ .Value }}" },
            { type = "pg_dsn", name = "DEMO_DSN", database = "demo" }
          ]
          optional_secrets = ["DEMO_OPTIONAL"]
        TOML
      )

      entry = ToolCatalog.new(roots: [ root ]).entries.sole

      assert_equal "demo", entry.name
      assert_equal "research", entry.category
      assert_equal "Demo tool", entry.description
      assert_equal 2, entry.required_secret_count
      assert_equal 1, entry.optional_secret_count
      assert_equal "static", entry.secrets.first.kind
      assert_equal "pg_dsn", entry.secrets.second.kind
      assert_equal "DEMO_DSN", entry.secrets.second.secret_ref
      assert_equal "demo", entry.secrets.second.database
      assert_equal "DEMO_OPTIONAL", entry.secrets.third.name
      assert_not entry.secrets.third.required?
    end
  end

  test "later roots shadow earlier tool manifests with the same tool name" do
    Dir.mktmpdir do |base|
      Dir.mktmpdir do |overlay|
        [ [ base, "BASE_TOKEN" ], [ overlay, "OVERLAY_TOKEN" ] ].each do |root, token|
          tool_dir = File.join(root, "tools", "alpha")
          FileUtils.mkdir_p(tool_dir)
          File.write(
            File.join(tool_dir, "pyproject.toml"),
            <<~TOML
              [tool.centaur]
              hosts = ["api.example.com"]
              secrets = [{ name = "#{token}", match_headers = ["Authorization"] }]
            TOML
          )
        end

        entry = ToolCatalog.new(roots: [ base, overlay ]).entries.sole

        assert_equal "alpha", entry.name
        assert_equal "OVERLAY_TOKEN", entry.secrets.sole.name
      end
    end
  end
end
