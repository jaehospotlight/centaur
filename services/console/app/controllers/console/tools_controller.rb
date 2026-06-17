module Console
  # Read-only catalog of discovered tool manifests from TOOL_DIRS. The console
  # uses this to show operators which tools are available before credential
  # requirement binding is added.
  class ToolsController < ApplicationController
    layout "console"

    def index
      @catalog = ToolCatalog.new
      @tools = @catalog.tools
    end
  end
end
