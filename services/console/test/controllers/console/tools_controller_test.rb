require "test_helper"
require "tmpdir"

class Console::ToolsControllerTest < ActionDispatch::IntegrationTest
  setup do
    @operator = users(:acme_admin)
    post login_url, params: { email: @operator.email, password: "password123456" }
  end

  test "lists tools discovered from TOOL_DIRS" do
    Dir.mktmpdir do |dir|
      tools_root = Pathname.new(dir)
      write_tool(tools_root.join("media", "veo3"), <<~TOML)
        [tool.centaur]
        module = "client.py"
        secrets = [
          {type = "http", name = "GOOGLE_API_KEY", mode = "inject", inject_header = "x-goog-api-key", hosts = ["generativelanguage.googleapis.com"]},
        ]
      TOML

      with_tool_dirs(tools_root.to_s) do
        get console_tools_url
      end

      assert_response :ok
      assert_select "h1", text: "Tools"
      assert_select "td", text: /veo3/
      assert_select "span", text: "GOOGLE_API_KEY"
      assert_select "span", text: "generativelanguage.googleapis.com"
    end
  end

  test "later TOOL_DIRS entries shadow tools with the same name" do
    Dir.mktmpdir do |first|
      Dir.mktmpdir do |second|
        write_tool(Pathname.new(first).join("media", "shared"), <<~TOML)
          [tool.centaur]
          module = "old.py"
          secrets = ["OLD_SECRET"]
        TOML
        write_tool(Pathname.new(second).join("shared"), <<~TOML)
          [tool.centaur]
          module = "new.py"
          secrets = ["NEW_SECRET"]
        TOML

        with_tool_dirs("#{first}:#{second}") do
          get console_tools_url
        end

        assert_response :ok
        assert_select "td", text: /shared/
        assert_select "span", text: "NEW_SECRET"
        assert_select "body", text: /OLD_SECRET/, count: 0
      end
    end
  end

  test "skips persona manifests" do
    Dir.mktmpdir do |dir|
      tools_root = Pathname.new(dir)
      write_tool(tools_root.join("personas", "eng"), <<~TOML)
        [tool.centaur]
        type = "persona"
      TOML

      with_tool_dirs(tools_root.to_s) do
        get console_tools_url
      end

      assert_response :ok
      assert_select "p", text: /No tools discovered/
    end
  end

  private

  def write_tool(path, pyproject)
    path.mkpath
    path.join("pyproject.toml").write(pyproject)
  end

  def with_tool_dirs(value)
    old = ENV["TOOL_DIRS"]
    ENV["TOOL_DIRS"] = value
    yield
  ensure
    ENV["TOOL_DIRS"] = old
  end
end
