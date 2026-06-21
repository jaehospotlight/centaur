require "test_helper"
require "fileutils"
require "tmpdir"

module Console
  class ToolsControllerTest < ActionDispatch::IntegrationTest
    setup do
      @operator = users(:acme_admin)
      post login_url, params: { email: @operator.email, password: "password123456" }
    end

    test "redirects to login when not signed in" do
      delete logout_url

      get console_tools_url

      assert_redirected_to login_path
    end

    test "index lists discovered tools" do
      with_catalog_entry do |entry|
        ToolCatalog.stub(:entries, [ entry ]) do
          get console_tools_url
        end

        assert_response :ok
        assert_match "demo", response.body
        assert_match "1 required", response.body
      end
    end

    test "show renders secret requirements and matching existing secrets" do
      secret = StaticSecret.create!(
        namespace: "acme",
        foreign_id: "tool-demo-demo-api-key",
        name: "DEMO_API_KEY",
        labels: { "centaur-tool" => "demo" },
        inject_config: { "header" => "Authorization" },
        created_by: @operator
      )
      secret.create_source!(source_type: "env", config: { "var" => "DEMO_API_KEY" })

      with_catalog_entry do |entry|
        ToolCatalog.stub(:find!, entry) do
          get console_tool_url(entry.key)
        end

        assert_response :ok
        assert_match "Secret Requirements", response.body
        assert_match "tool-demo-demo-api-key", response.body
        assert_match secret.oid, response.body
        assert_match "Add Secret", response.body
      end
    end

    test "prefilled add secret link opens the static secret form" do
      with_catalog_entry do |entry|
        ToolCatalog.stub(:find!, entry) do
          get console_tool_url(entry.key)
        end

        assert_response :ok
        path = response.body.match(%r{href="([^"]*/console/secrets/static/new[^"]+)"})[1]
        get path.gsub("&amp;", "&")

        assert_response :ok
        assert_match "tool-demo-demo-api-key", response.body
        assert_match "DEMO_API_KEY", response.body
        assert_match "api.example.com", response.body
      end
    end

    private

    def with_catalog_entry
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
              { type = "http", name = "DEMO_API_KEY", mode = "inject", inject_header = "Authorization", inject_formatter = "Bearer {{ .Value }}" }
            ]
          TOML
        )

        yield ToolCatalog.new(roots: [ root ]).entries.sole
      end
    end
  end
end
