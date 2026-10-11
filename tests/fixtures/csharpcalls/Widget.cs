using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Shop.Core;

public interface IStore
{
    Task<Widget> FindAsync(string id);
    List<Widget> All();
}

public class Widget
{
    public string Name { get; set; }
    public Widget() { }
    public string Label() => Name;
    public static Widget Make(string n) => new() { Name = n };
}

public class Plain { }

public static class WidgetExtensions
{
    public static string Shout(this Widget w) => w.Name.ToUpper();
}

public class Base
{
    public Base(int x) { }
    protected string Greet() => "hi";
}
