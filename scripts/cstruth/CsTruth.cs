// Ground truth for the C# extractor, read from Roslyn's syntax trees and semantic model.
//
//   dotnet CsTruth.dll --root <repo> > truth.jsonl
//
// Every *.cs under --root (minus bin/obj) is one compilation, bound against the .NET and ASP.NET
// Core reference assemblies of the installed runtime. NuGet packages are not available, so calls
// into them stay unresolved and are ignored; calls into the repository bind. Rows, one JSON object
// per line:
//   type   {fqn, kind, file, line}
//   method {owner, name, ctor, mods, file, line}      name "<init>" for constructors (incl. primary)
//   field  {owner, name, kind, mods, file, line}      field | property | event | enum member
//   call   {file, line, caller, name, target, how}    target "Decl#name" (or "Decl.name" for how=member)
//                                                     only when declared under --root. how: invoke |
//                                                     new | ctor (: base()/this()) | ref (method group)
//                                                     | member (property/field/event read or write)
//   xcall  {file, line, caller, name, target, how}    a call Roslyn bound outside the repository
//                                                     (target "outside:Type#name") or could not bind
//                                                     (target ""): for the precision check only
//   cfg    {file, line, api, key}                     IConfiguration / environment read; key is what
//                                                     Roslyn folds to a constant ("" = computed)
//   route  {file, line, verb, path, handler}          ASP.NET attribute routing, partial parts merged,
//                                                     [controller]/[action] applied, inherited [Route]
//   table  {name, file, line, how}                    EF Core table: DbSet<T> (name per convention,
//                                                     [Table], ToTable), CreateTable(name:)
using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

static class Truth
{
    static string root;
    static readonly StringBuilder Out = new();
    static Compilation comp;

    static string Esc(string s)
    {
        var b = new StringBuilder();
        foreach (var c in s ?? "")
        {
            if (c == '"' || c == '\\') b.Append('\\').Append(c);
            else if (c < 32) b.Append(' ');
            else b.Append(c);
        }
        return b.ToString();
    }

    static void Row(string type, params object[] kv)
    {
        var b = new StringBuilder("{\"t\":\"" + type + "\"");
        for (int i = 0; i < kv.Length; i += 2)
        {
            b.Append(",\"").Append(kv[i]).Append("\":");
            var v = kv[i + 1];
            if (v is int || v is bool) b.Append(v is bool bb ? (bb ? "true" : "false") : v.ToString());
            else b.Append('"').Append(Esc(v?.ToString())).Append('"');
        }
        Out.Append(b).Append("}\n");
    }

    static string Rel(SyntaxTree t) => Path.GetRelativePath(root, t.FilePath).Replace('\\', '/');
    static int Line(SyntaxToken t) => t.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
    static int Line(SyntaxNode n) => n.GetLocation().GetLineSpan().StartLinePosition.Line + 1;

    static string TypeFqn(ISymbol t)
    {
        if (t == null) return "";
        var parts = new List<string>();
        for (ISymbol s = t; s != null && !(s is INamespaceSymbol ns && ns.IsGlobalNamespace); s = s.ContainingSymbol)
            if (s is INamedTypeSymbol || s is INamespaceSymbol) parts.Add(s.Name);
            else if (s is IMethodSymbol || s is IPropertySymbol || s is IFieldSymbol) continue;
        parts.Reverse();
        return string.Join(".", parts);
    }

    static bool InRepo(ISymbol s) =>
        s != null && s.DeclaringSyntaxReferences.Any(r => r.SyntaxTree.FilePath.StartsWith(root));

    static string Mods(ISymbol s) => s.DeclaredAccessibility.ToString().ToLowerInvariant();

    static string Caller(SyntaxNode n, SemanticModel m)
    {
        for (var p = n; p != null; p = p.Parent)
        {
            if (p is BaseMethodDeclarationSyntax || p is PropertyDeclarationSyntax || p is FieldDeclarationSyntax
                || p is EventDeclarationSyntax || p is AccessorDeclarationSyntax || p is TypeDeclarationSyntax)
            {
                if (p is AccessorDeclarationSyntax) continue;
                var sym = m.GetDeclaredSymbol(p);
                if (sym == null && p is FieldDeclarationSyntax f)
                    sym = m.GetDeclaredSymbol(f.Declaration.Variables[0]);
                if (sym != null) return TypeFqn(sym.ContainingType ?? sym) + "#" + sym.Name;
            }
        }
        return "";
    }

    public static int Main(string[] args)
    {
        for (int i = 0; i < args.Length; i++) if (args[i] == "--root") root = Path.GetFullPath(args[++i]);
        if (root == null) { Console.Error.WriteLine("usage: --root DIR"); return 2; }
        var files = Directory.EnumerateFiles(root, "*.cs", SearchOption.AllDirectories)
            .Where(f => !f.Contains("/bin/") && !f.Contains("/obj/") && !f.Contains("/.git/"))
            .OrderBy(f => f, StringComparer.Ordinal).ToList();
        var opts = new CSharpParseOptions(LanguageVersion.Latest);
        var trees = files.Select(f => CSharpSyntaxTree.ParseText(File.ReadAllText(f), opts, f)).ToList();
        var refs = new List<MetadataReference>();
        var rt = System.Runtime.InteropServices.RuntimeEnvironment.GetRuntimeDirectory();   // .../shared/Microsoft.NETCore.App/x/
        var dotnet = Path.GetFullPath(Path.Combine(rt, "../../.."));
        foreach (var pack in new[] { "Microsoft.NETCore.App.Ref", "Microsoft.AspNetCore.App.Ref" })
        {
            var packDir = Path.Combine(dotnet, "packs", pack);
            if (!Directory.Exists(packDir)) continue;
            var v = Directory.GetDirectories(packDir).OrderBy(d => d).Last();
            var refDir = Directory.GetDirectories(Path.Combine(v, "ref")).First();
            refs.AddRange(Directory.GetFiles(refDir, "*.dll").Select(d => MetadataReference.CreateFromFile(d)));
        }
        comp = CSharpCompilation.Create("truth", trees, refs,
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary, nullableContextOptions: NullableContextOptions.Enable));
        int errors = comp.GetDiagnostics().Count(d => d.Severity == DiagnosticSeverity.Error);
        foreach (var g in comp.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).GroupBy(d => d.Id).OrderByDescending(g => g.Count()).Take(6))
            Console.Error.WriteLine("  " + g.Key + " x" + g.Count() + "  " + g.First().GetMessage());
        Console.Error.WriteLine("files=" + files.Count + " refs=" + refs.Count + " errors=" + errors);

        foreach (var tree in trees)
        {
            var model = comp.GetSemanticModel(tree);
            var rootNode = tree.GetRoot();
            string file = Rel(tree);
            Declarations(rootNode, model, file);
            Calls(rootNode, model, file);
            Config(rootNode, model, file);
        }
        Routes(trees);
        Tables(trees);
        Console.Out.Write(Out.ToString());
        return 0;
    }

    // ------------------------------------------------------------------ declarations

    static void Declarations(SyntaxNode rootNode, SemanticModel model, string file)
    {
        foreach (var n in rootNode.DescendantNodes())
        {
            switch (n)
            {
                case BaseTypeDeclarationSyntax td:
                {
                    var s = model.GetDeclaredSymbol(td);
                    if (s == null) break;
                    Row("type", "fqn", TypeFqn(s), "kind", td.Kind().ToString().Replace("Declaration", "").ToLowerInvariant(),
                        "file", file, "line", Line(td.Identifier));
                    if (td is TypeDeclarationSyntax tds && tds.ParameterList != null && !(td is RecordDeclarationSyntax))
                        Row("method", "owner", TypeFqn(s), "name", "<init>", "ctor", true, "mods", "public", "file", file, "line", Line(td.Identifier));
                    if (td is RecordDeclarationSyntax rd && rd.ParameterList != null)
                    {
                        Row("method", "owner", TypeFqn(s), "name", "<init>", "ctor", true, "mods", "public", "file", file, "line", Line(td.Identifier));
                        foreach (var p in rd.ParameterList.Parameters)
                            Row("field", "owner", TypeFqn(s), "name", p.Identifier.Text, "kind", "property", "mods", "public", "file", file, "line", Line(p.Identifier));
                    }
                    break;
                }
                case DelegateDeclarationSyntax dd:
                {
                    var s = model.GetDeclaredSymbol(dd);
                    if (s != null) Row("type", "fqn", TypeFqn(s), "kind", "delegate", "file", file, "line", Line(dd.Identifier));
                    break;
                }
                case MethodDeclarationSyntax md:
                {
                    var s = model.GetDeclaredSymbol(md);
                    if (s == null) break;
                    Row("method", "owner", TypeFqn(s.ContainingType), "name", md.Identifier.Text, "ctor", false,
                        "mods", Mods(s), "file", file, "line", Line(md.Identifier));
                    break;
                }
                case ConstructorDeclarationSyntax cd:
                {
                    var s = model.GetDeclaredSymbol(cd);
                    if (s == null) break;
                    Row("method", "owner", TypeFqn(s.ContainingType), "name", "<init>", "ctor", true,
                        "mods", Mods(s), "file", file, "line", Line(cd.Identifier));
                    break;
                }
                case PropertyDeclarationSyntax pd:
                {
                    var s = model.GetDeclaredSymbol(pd);
                    if (s != null) Row("field", "owner", TypeFqn(s.ContainingType), "name", pd.Identifier.Text, "kind", "property",
                        "mods", Mods(s), "file", file, "line", Line(pd.Identifier));
                    break;
                }
                case VariableDeclaratorSyntax vd when vd.Parent?.Parent is FieldDeclarationSyntax || vd.Parent?.Parent is EventFieldDeclarationSyntax:
                {
                    var s = model.GetDeclaredSymbol(vd);
                    if (s != null) Row("field", "owner", TypeFqn(s.ContainingType), "name", vd.Identifier.Text,
                        "kind", s is IEventSymbol ? "event" : "field", "mods", Mods(s), "file", file, "line", Line(vd.Identifier));
                    break;
                }
                case EnumMemberDeclarationSyntax em:
                {
                    var s = model.GetDeclaredSymbol(em);
                    if (s != null) Row("field", "owner", TypeFqn(s.ContainingType), "name", em.Identifier.Text, "kind", "enum",
                        "mods", "public", "file", file, "line", Line(em.Identifier));
                    break;
                }
            }
        }
    }

    // ------------------------------------------------------------------ calls

    static void Call(SemanticModel model, SyntaxNode at, SyntaxToken nameTok, ISymbol sym, string how, string file)
    {
        string seen = (how == "new" || how == "ctor") ? "<init>" : nameTok.Text;
        if (sym == null)
        {
            // Roslyn could not bind it (a NuGet type in the way): a call the index may still be right about
            if (how != "member") Row("xcall", "file", file, "line", Line(nameTok), "caller", Caller(at, model), "name", seen, "target", "", "how", how);
            return;
        }
        if (sym is IMethodSymbol ms)
        {
            ms = ms.ReducedFrom ?? ms;
            sym = ms.OriginalDefinition;
        }
        else sym = sym.OriginalDefinition;
        if (!InRepo(sym) || sym.ContainingType == null)
        {
            // bound outside the repository (BCL, NuGet, an implicit constructor): an index row naming a repo method here is wrong
            if (how != "member") Row("xcall", "file", file, "line", Line(nameTok), "caller", Caller(at, model), "name", seen, "target", "outside:" + (sym.ContainingType?.ToDisplayString() ?? "") + "#" + sym.Name, "how", how);
            return;
        }
        string name = sym.Name;
        if (sym is IMethodSymbol m2 && (m2.MethodKind == MethodKind.Constructor || m2.MethodKind == MethodKind.StaticConstructor)) name = "<init>";
        string target = (how == "member")
            ? TypeFqn(sym.ContainingType) + "." + name
            : TypeFqn(sym.ContainingType) + "#" + name;
        Row("call", "file", file, "line", Line(nameTok), "caller", Caller(at, model), "name", name, "target", target, "how", how);
    }

    static void Calls(SyntaxNode rootNode, SemanticModel model, string file)
    {
        foreach (var n in rootNode.DescendantNodes())
        {
            switch (n)
            {
                case InvocationExpressionSyntax inv:
                {
                    var info = model.GetSymbolInfo(inv);
                    var sym = info.Symbol ?? (info.CandidateSymbols.Length == 1 ? info.CandidateSymbols[0] : null);
                    if (sym is IMethodSymbol { MethodKind: MethodKind.LocalFunction } ) break;
                    if (sym is IMethodSymbol dm && dm.MethodKind == MethodKind.DelegateInvoke) break;
                    var tok = NameToken(inv.Expression);
                    Call(model, inv, tok, sym, "invoke", file);
                    break;
                }
                case ObjectCreationExpressionSyntax oc:
                {
                    var info = model.GetSymbolInfo(oc);
                    var sym = info.Symbol ?? (info.CandidateSymbols.Length == 1 ? info.CandidateSymbols[0] : null);
                    Call(model, oc, oc.NewKeyword, sym, "new", file);
                    break;
                }
                case ImplicitObjectCreationExpressionSyntax io:
                {
                    var sym = model.GetSymbolInfo(io).Symbol;
                    Call(model, io, io.NewKeyword, sym, "new", file);
                    break;
                }
                case ConstructorInitializerSyntax ci:
                {
                    Call(model, ci, ci.ThisOrBaseKeyword, model.GetSymbolInfo(ci).Symbol, "ctor", file);
                    break;
                }
                case SimpleNameSyntax name:
                {
                    // method groups and property/field reads: a name that is not the callee of an invocation
                    if (name.Parent is InvocationExpressionSyntax pi && pi.Expression == name) break;
                    if (name.Parent is MemberAccessExpressionSyntax pm && pm.Name == name && pm.Parent is InvocationExpressionSyntax pi2 && pi2.Expression == pm) break;
                    if (name.Parent is MemberBindingExpressionSyntax pb && pb.Name == name && pb.Parent is InvocationExpressionSyntax pi3 && pi3.Expression == pb) break;
                    if (name.Parent is MemberAccessExpressionSyntax pm2 && pm2.Expression == name && pm2.Name != name) { /* receiver identifier, handled as itself */ }
                    if (name.Parent is NameColonSyntax || name.Parent is NameEqualsSyntax || name.Parent is AttributeSyntax || name.Parent is QualifiedNameSyntax) break;
                    if (name.Parent is NameMemberCrefSyntax) break;
                    if (IsNameof(name)) break;
                    if (name.Parent is AssignmentExpressionSyntax ae && ae.Parent is InitializerExpressionSyntax && ae.Left == name) { /* object initializer: member write */ }
                    var info = model.GetSymbolInfo(name);
                    var sym = info.Symbol;
                    if (sym is IMethodSymbol gm && (gm.MethodKind == MethodKind.Ordinary))
                        Call(model, name, name.Identifier, sym, "ref", file);
                    else if (sym is IPropertySymbol || sym is IFieldSymbol || sym is IEventSymbol)
                    {
                        if (sym is IFieldSymbol fs && fs.ContainingType.TypeKind == TypeKind.Enum) { Call(model, name, name.Identifier, sym, "member", file); break; }
                        Call(model, name, name.Identifier, sym, "member", file);
                    }
                    break;
                }
            }
        }
    }

    static bool IsNameof(SyntaxNode n)
    {
        for (var p = n.Parent; p != null; p = p.Parent)
        {
            if (p is InvocationExpressionSyntax i && i.Expression is IdentifierNameSyntax id && id.Identifier.Text == "nameof") return true;
            if (p is StatementSyntax || p is MemberDeclarationSyntax) return false;
        }
        return false;
    }

    static SyntaxToken NameToken(ExpressionSyntax e)
    {
        switch (e)
        {
            case MemberAccessExpressionSyntax m: return m.Name.Identifier;
            case MemberBindingExpressionSyntax b: return b.Name.Identifier;
            case IdentifierNameSyntax i: return i.Identifier;
            case GenericNameSyntax g: return g.Identifier;
            case ConditionalAccessExpressionSyntax c: return NameToken(c.WhenNotNull);
            default: return e.GetFirstToken();
        }
    }

    // ------------------------------------------------------------------ config

    static string Fold(SemanticModel model, ExpressionSyntax e)
    {
        var c = model.GetConstantValue(e);
        return c.HasValue && c.Value is string s ? s : "";
    }

    static bool IsCfgType(ITypeSymbol t)
    {
        for (; t != null; t = t.BaseType)
        {
            if (t.Name is "IConfiguration" or "IConfigurationSection" or "IConfigurationRoot" or "ConfigurationManager") return true;
            if (t.AllInterfaces.Any(i => i.Name is "IConfiguration" or "IConfigurationSection" or "IConfigurationRoot")) return true;
        }
        return false;
    }

    // the key prefix contributed by `.GetSection("A")` links on the receiver chain, "" + dynamic flag
    static (string prefix, bool known) Prefix(SemanticModel model, ExpressionSyntax recv)
    {
        recv = recv is ParenthesizedExpressionSyntax p ? p.Expression : recv;
        if (recv is InvocationExpressionSyntax inv && inv.Expression is MemberAccessExpressionSyntax ma
            && ma.Name.Identifier.Text is "GetSection" or "GetRequiredSection" && inv.ArgumentList.Arguments.Count == 1)
        {
            var (pp, pk) = Prefix(model, ma.Expression);
            var k = Fold(model, inv.ArgumentList.Arguments[0].Expression);
            if (k == "" || !pk) return ("", false);
            return (pp == "" ? k : pp + ":" + k, true);
        }
        if (recv is ConditionalAccessExpressionSyntax) return ("", true);
        return ("", true);
    }

    static void Config(SyntaxNode rootNode, SemanticModel model, string file)
    {
        foreach (var n in rootNode.DescendantNodes())
        {
            if (n is InvocationExpressionSyntax inv)
            {
                var info = model.GetSymbolInfo(inv);
                var sym = info.Symbol as IMethodSymbol ?? info.CandidateSymbols.OfType<IMethodSymbol>().FirstOrDefault();
                ExpressionSyntax recv = null;
                string name = null;
                if (inv.Expression is MemberAccessExpressionSyntax ma) { recv = ma.Expression; name = ma.Name.Identifier.Text; }
                else if (inv.Expression is MemberBindingExpressionSyntax mb) { name = mb.Name.Identifier.Text; }
                if (name == null) continue;
                var args = inv.ArgumentList.Arguments;
                if (name == "GetEnvironmentVariable" && (sym?.ContainingType?.Name == "Environment" || recv?.ToString() is "Environment" or "System.Environment") && args.Count >= 1)
                {
                    Row("cfg", "file", file, "line", Line(NameToken(inv.Expression)), "api", "env", "key", Fold(model, args[0].Expression));
                    continue;
                }
                if (name is "GetValue" or "GetSection" or "GetRequiredSection" or "GetConnectionString" or "Get" or "Bind" or "GetChildren" or "Exists")
                {
                    var rt = sym == null ? null : (sym.ReducedFrom != null ? sym.ReceiverType : sym.ContainingType);
                    var recvType = recv == null ? null : model.GetTypeInfo(recv).Type;
                    if (!(IsCfgType(recvType) || (sym != null && sym.ContainingNamespace?.ToString().StartsWith("Microsoft.Extensions.Configuration") == true))) continue;
                    if (name is "GetChildren" or "Exists") continue;
                    var (pre, known) = recv == null ? ("", true) : Prefix(model, recv);
                    string key;
                    if (name is "Get" or "Bind")
                    {
                        // section binding: the key is the section path of the receiver
                        if (!(recv is InvocationExpressionSyntax)) continue;   // root binding has no key
                        var (kp, kk) = Prefix(model, recv is InvocationExpressionSyntax ri && ri.Expression is MemberAccessExpressionSyntax rm && rm.Name.Identifier.Text is "GetSection" or "GetRequiredSection" ? recv : recv);
                        // Prefix() describes the receiver's own chain; bind reads the last GetSection too
                        var last = recv as InvocationExpressionSyntax;
                        if (last?.Expression is MemberAccessExpressionSyntax lm && lm.Name.Identifier.Text is "GetSection" or "GetRequiredSection")
                        {
                            var (p2, k2) = Prefix(model, recv);
                            key = k2 ? p2 : "";
                            Row("cfg", "file", file, "line", Line(NameToken(inv.Expression)), "api", name.ToLower(), "key", key);
                        }
                        continue;
                    }
                    if (args.Count == 0) continue;
                    var k0 = Fold(model, args[0].Expression);
                    if (name == "GetConnectionString") key = k0 == "" ? "" : "ConnectionStrings:" + k0;
                    else key = (k0 == "" || !known) ? "" : (pre == "" ? k0 : pre + ":" + k0);
                    Row("cfg", "file", file, "line", Line(NameToken(inv.Expression)), "api", name.ToLower(), "key", key);
                }
            }
            else if (n is ElementAccessExpressionSyntax ea && ea.ArgumentList.Arguments.Count == 1)
            {
                var t = model.GetTypeInfo(ea.Expression).Type;
                if (!IsCfgType(t)) continue;
                var (pre, known) = Prefix(model, ea.Expression);
                var k0 = Fold(model, ea.ArgumentList.Arguments[0].Expression);
                Row("cfg", "file", file, "line", Line(ea.ArgumentList.OpenBracketToken), "api", "indexer", "key", (k0 == "" || !known) ? "" : (pre == "" ? k0 : pre + ":" + k0));
            }
        }
    }

    // ------------------------------------------------------------------ routes

    static readonly Dictionary<string, string> Verbs = new()
    {
        ["HttpGet"] = "GET", ["HttpPost"] = "POST", ["HttpPut"] = "PUT", ["HttpDelete"] = "DELETE",
        ["HttpPatch"] = "PATCH", ["HttpHead"] = "HEAD", ["HttpOptions"] = "OPTIONS",
    };

    static string AttrName(AttributeSyntax a)
    {
        var n = a.Name.ToString();
        n = n.Substring(n.LastIndexOf('.') + 1);
        return n.EndsWith("Attribute") ? n[..^9] : n;
    }

    static string Template(SemanticModel model, AttributeSyntax a)
    {
        var args = a.ArgumentList?.Arguments;
        if (args == null || args.Value.Count == 0) return null;
        var first = args.Value.FirstOrDefault(x => x.NameEquals == null || x.NameEquals.Name.Identifier.Text == "template");
        if (first == null) return null;
        return Fold(model, first.Expression);
    }

    static IEnumerable<AttributeSyntax> Attrs(SyntaxList<AttributeListSyntax> lists) => lists.SelectMany(l => l.Attributes);

    static void Routes(List<SyntaxTree> trees)
    {
        // class symbol -> route templates declared on any part
        foreach (var tree in trees)
        {
            var model = comp.GetSemanticModel(tree);
            foreach (var cd in tree.GetRoot().DescendantNodes().OfType<ClassDeclarationSyntax>())
            {
                var cs = model.GetDeclaredSymbol(cd);
                if (cs == null || cs.IsAbstract) continue;
                if (!IsController(cs)) continue;
                var templates = new List<string>();
                for (var t = cs; t != null && t.SpecialType != SpecialType.System_Object; t = t.BaseType)
                {
                    var found = new List<string>();
                    foreach (var part in t.DeclaringSyntaxReferences)
                    {
                        var pm = comp.GetSemanticModel(part.SyntaxTree);
                        foreach (var a in Attrs(((ClassDeclarationSyntax)part.GetSyntax()).AttributeLists))
                            if (AttrName(a) == "Route") found.Add(Template(pm, a) ?? "");
                    }
                    if (found.Count > 0) { templates = found; break; }
                }
                string ctrl = cs.Name.EndsWith("Controller") ? cs.Name[..^10] : cs.Name;
                foreach (var md in cd.Members.OfType<MethodDeclarationSyntax>())
                {
                    var ms = model.GetDeclaredSymbol(md);
                    if (ms == null || ms.DeclaredAccessibility != Accessibility.Public || ms.IsStatic) continue;
                    if (Attrs(md.AttributeLists).Any(a => AttrName(a) == "NonAction")) continue;
                    var verbAttrs = Attrs(md.AttributeLists).Where(a => Verbs.ContainsKey(AttrName(a))).ToList();
                    var routeAttrs = Attrs(md.AttributeLists).Where(a => AttrName(a) == "Route").ToList();
                    if (verbAttrs.Count == 0 && routeAttrs.Count == 0) continue;
                    // each verb attribute is one action selector; a template on it (or a [Route]) is the method part
                    var selectors = new List<(string verb, string tpl)>();
                    foreach (var v in verbAttrs) selectors.Add((Verbs[AttrName(v)], Template(model, v)));
                    if (verbAttrs.Count == 0) foreach (var r in routeAttrs) selectors.Add(("ANY", Template(model, r) ?? ""));
                    else if (verbAttrs.All(v => Template(model, v) == null) && routeAttrs.Count > 0)
                    {
                        var expanded = new List<(string, string)>();
                        foreach (var v in verbAttrs) foreach (var r in routeAttrs) expanded.Add((Verbs[AttrName(v)], Template(model, r) ?? ""));
                        selectors = expanded;
                    }
                    foreach (var (verb, tpl) in selectors)
                    {
                        var bases = templates.Count == 0 ? new List<string> { null } : templates;
                        foreach (var b in bases)
                        {
                            string path;
                            if (tpl != null && (tpl.StartsWith("/") || tpl.StartsWith("~/"))) path = tpl.TrimStart('~');
                            else if (b == null) path = tpl ?? "";
                            else if (string.IsNullOrEmpty(tpl)) path = b;
                            else path = b.TrimEnd('/') + "/" + tpl.TrimStart('/');
                            path = path.Replace("[controller]", ctrl).Replace("[action]", ms.Name);
                            Row("route", "file", Rel(tree), "line", Line(md.Identifier), "verb", verb, "path", path.Trim('/'),
                                "handler", TypeFqn(cs) + "#" + ms.Name);
                        }
                    }
                }
            }
        }
    }

    static bool IsController(INamedTypeSymbol cs)
    {
        for (var t = cs; t != null; t = t.BaseType)
        {
            if (t.Name is "ControllerBase" or "Controller") return true;
            foreach (var a in t.GetAttributes()) if (a.AttributeClass?.Name == "ApiControllerAttribute") return true;
        }
        return cs.Name.EndsWith("Controller");
    }

    // ------------------------------------------------------------------ tables

    static void Tables(List<SyntaxTree> trees)
    {
        var explicitName = new Dictionary<string, string>();     // entity simple name -> table name from ToTable / [Table]
        var noTable = new HashSet<string>();                      // ToView(null) / ToTable((string)null)
        var sets = new List<(string entity, string prop, string file, int line)>();
        foreach (var tree in trees)
        {
            string file = Rel(tree);
            var model = comp.GetSemanticModel(tree);
            foreach (var n in tree.GetRoot().DescendantNodes())
            {
                if (n is PropertyDeclarationSyntax pd && pd.Type is GenericNameSyntax g && g.Identifier.Text == "DbSet" && g.TypeArgumentList.Arguments.Count == 1
                    && !file.Contains("/Migrations/"))
                    sets.Add((g.TypeArgumentList.Arguments[0].ToString().Split('.').Last(), pd.Identifier.Text, file, Line(pd.Identifier)));
                else if (n is ClassDeclarationSyntax cd)
                {
                    foreach (var a in Attrs(cd.AttributeLists))
                        if (AttrName(a) == "Table") { var t = Template(model, a); if (!string.IsNullOrEmpty(t)) { explicitName[cd.Identifier.Text] = t; Row("table", "name", t, "file", file, "line", Line(a), "how", "attribute"); } }
                }
                else if (n is InvocationExpressionSyntax inv && inv.Expression is MemberAccessExpressionSyntax ma)
                {
                    string nm = ma.Name.Identifier.Text;
                    if (nm is "ToTable" or "ToView")
                    {
                        var arg = inv.ArgumentList.Arguments.FirstOrDefault()?.Expression;
                        // find the entity: modelBuilder.Entity<T>(...) lambda or .Entity<T>().ToTable
                        string ent = null;
                        for (var p = inv.Parent; p != null; p = p.Parent)
                            if (p is InvocationExpressionSyntax pi && pi.Expression is MemberAccessExpressionSyntax pma
                                && pma.Name is GenericNameSyntax pg && pg.Identifier.Text == "Entity") { ent = pg.TypeArgumentList.Arguments[0].ToString().Split('.').Last(); break; }
                        if (ent == null && ma.Expression is InvocationExpressionSyntax ci && ci.Expression is MemberAccessExpressionSyntax cma
                            && cma.Name is GenericNameSyntax cg && cg.Identifier.Text == "Entity") ent = cg.TypeArgumentList.Arguments[0].ToString().Split('.').Last();
                        bool nullArg = arg == null || arg.ToString() is "null" or "(string)null" or "(string?)null";
                        if (arg != null && !nullArg && model.GetConstantValue(arg).Value is string s && s != "")
                        {
                            if (ent != null) explicitName[ent] = s;
                            if (!file.Contains("/Migrations/")) Row("table", "name", s, "file", file, "line", Line(inv), "how", "totable");
                        }
                        else if (nullArg && ent != null) noTable.Add(ent);
                    }
                    else if (nm == "CreateTable")
                    {
                        var nameArg = inv.ArgumentList.Arguments.FirstOrDefault(a => a.NameColon?.Name.Identifier.Text == "name") ?? inv.ArgumentList.Arguments.FirstOrDefault();
                        if (nameArg != null && model.GetConstantValue(nameArg.Expression).Value is string s2)
                            Row("table", "name", s2, "file", file, "line", Line(inv), "how", "migration");
                    }
                }
            }
        }
        foreach (var (entity, prop, file, line) in sets)
        {
            if (noTable.Contains(entity)) continue;
            Row("table", "name", explicitName.TryGetValue(entity, out var t) ? t : prop, "file", file, "line", line, "how", "dbset");
        }
    }
}
