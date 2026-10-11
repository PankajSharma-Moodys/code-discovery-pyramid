// Ground truth for the Java extractor, read from javac's own trees.
//
//   java scripts/JavaTruth.java --root <repo> [--stubs <dir>] [--classpath <cp>] > truth.jsonl
//
// Every *.java under --root is parsed and attributed (errors tolerated: a missing
// dependency leaves its calls unresolved, they are then reported with target ""
// and ignored by the benchmark). --stubs is a source path for types the repo
// uses but does not contain. Rows, one JSON object per line:
//   type   {fqn, kind, file, line}
//   method {owner, name, ctor, iface, mods, file, line, end}      name "<init>" for constructors
//   field  {owner, name, static, final, file, line}
//   call   {file, line, caller, name, target, how}                target "Decl#name" only
//                                                                 when declared under --root
//   cfg    {file, line, api, key}     a read of the process environment or a JVM system property:
//                                     System.getenv(k), System.getProperty(k[,d]), Long.getLong,
//                                     Integer.getInteger, Boolean.getBoolean, System.getenv().getOrDefault(k,d)
//                                     / .get(k). key is the string javac can fold (literal, constant,
//                                     constant concatenation) or "" when it is computed.
// Only named (non-anonymous, non-local) classes contribute methods and fields.
// Calls inside lambdas and anonymous classes belong to the enclosing named member.
import com.sun.source.tree.*;
import com.sun.source.util.*;
import javax.lang.model.element.*;
import javax.tools.*;
import java.io.File;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class JavaTruth {
    static Trees trees;
    static Set<String> repoTypes = new HashSet<>();
    static Path root;
    static StringBuilder out = new StringBuilder();

    static String esc(String s) {
        StringBuilder b = new StringBuilder();
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c < 32) b.append(' ');
            else b.append(c);
        }
        return b.toString();
    }

    static void row(String type, String... kv) {
        StringBuilder b = new StringBuilder("{\"t\":\"" + type + "\"");
        for (int i = 0; i < kv.length; i += 2) {
            String v = kv[i + 1];
            boolean raw = v.equals("true") || v.equals("false") || v.matches("-?\\d+");
            b.append(",\"").append(kv[i]).append("\":");
            b.append(raw ? v : "\"" + esc(v) + "\"");
        }
        out.append(b).append("}\n");
    }

    public static void main(String[] args) throws Exception {
        String rootArg = null, stubs = null, cp = "";
        for (int i = 0; i < args.length; i++) {
            if (args[i].equals("--root")) rootArg = args[++i];
            else if (args[i].equals("--stubs")) stubs = args[++i];
            else if (args[i].equals("--classpath")) cp = args[++i];
        }
        root = Paths.get(rootArg).toAbsolutePath().normalize();
        List<File> files;
        try (Stream<Path> s = Files.walk(root)) {
            files = s.filter(p -> p.toString().endsWith(".java")).sorted().map(Path::toFile).collect(Collectors.toList());
        }
        JavaCompiler c = ToolProvider.getSystemJavaCompiler();
        StandardJavaFileManager fm = c.getStandardFileManager(null, null, null);
        List<String> opts = new ArrayList<>(List.of("-proc:none", "-Xlint:none", "-implicit:none", "-XDshould-stop.ifError=FLOW"));
        if (!cp.isEmpty()) { opts.add("-classpath"); opts.add(cp); }
        if (stubs != null) { opts.add("-sourcepath"); opts.add(stubs); }
        JavacTask task = (JavacTask) c.getTask(null, fm, d -> {}, opts, null, fm.getJavaFileObjectsFromFiles(files));
        List<CompilationUnitTree> cus = new ArrayList<>();
        for (CompilationUnitTree cu : task.parse()) cus.add(cu);
        task.analyze();
        trees = Trees.instance(task);
        for (CompilationUnitTree cu : cus) new Collect(cu).scan(cu, null);
        for (CompilationUnitTree cu : cus) new Visit(cu).scan(cu, null);
        System.out.print(out);
    }

    static String rel(CompilationUnitTree cu) {
        return root.relativize(Paths.get(cu.getSourceFile().toUri()).toAbsolutePath().normalize()).toString();
    }

    static boolean named(TypeElement te) {
        return te != null && (te.getNestingKind() == NestingKind.TOP_LEVEL || te.getNestingKind() == NestingKind.MEMBER);
    }

    static class Collect extends TreePathScanner<Void, Void> {
        final CompilationUnitTree cu;
        Collect(CompilationUnitTree cu) { this.cu = cu; }
        @Override public Void visitClass(ClassTree t, Void v) {
            TypeElement te = (TypeElement) trees.getElement(getCurrentPath());
            if (named(te)) repoTypes.add(te.getQualifiedName().toString());
            return super.visitClass(t, v);
        }
    }

    static int line(CompilationUnitTree cu, long pos) { return (int) cu.getLineMap().getLineNumber(pos); }

    static class Visit extends TreePathScanner<Void, Void> {
        final CompilationUnitTree cu;
        final SourcePositions sp = trees.getSourcePositions();
        String file;
        Deque<String> callers = new ArrayDeque<>();
        Visit(CompilationUnitTree cu) { this.cu = cu; this.file = rel(cu); }

        TypeElement owner(TreePath p) {
            while (p != null && !(p.getLeaf() instanceof ClassTree)) p = p.getParentPath();
            return p == null ? null : (TypeElement) trees.getElement(p);
        }

        @Override public Void visitClass(ClassTree t, Void v) {
            TypeElement te = (TypeElement) trees.getElement(getCurrentPath());
            if (named(te)) {
                String fqn = te.getQualifiedName().toString();
                row("type", "fqn", fqn, "kind", te.getKind().toString().toLowerCase(), "file", file,
                    "line", "" + line(cu, sp.getStartPosition(cu, t)));
                boolean iface = te.getKind() == ElementKind.INTERFACE || te.getKind() == ElementKind.ANNOTATION_TYPE;
                for (Tree m : t.getMembers()) {
                    if (m instanceof MethodTree mt) {
                        boolean ctor = mt.getName().contentEquals("<init>");
                        long start = sp.getStartPosition(cu, mt);
                        long cstart = sp.getStartPosition(cu, t);
                        if (ctor && sp.getEndPosition(cu, mt) < 0) continue; // implicit default constructor
                        if (start < 0) continue;
                        row("method", "owner", fqn, "name", ctor ? "<init>" : mt.getName().toString(),
                            "ctor", "" + ctor, "iface", "" + iface,
                            "mods", mt.getModifiers().getFlags().toString(),
                            "file", file, "line", "" + line(cu, start),
                            "end", "" + line(cu, Math.max(start, sp.getEndPosition(cu, mt) - 1)));
                    } else if (m instanceof VariableTree vt) {
                        Set<Modifier> f = vt.getModifiers().getFlags();
                        row("field", "owner", fqn, "name", vt.getName().toString(),
                            "static", "" + (f.contains(Modifier.STATIC) || iface), "final", "" + (f.contains(Modifier.FINAL) || iface),
                            "file", file, "line", "" + line(cu, sp.getStartPosition(cu, vt)));
                    }
                }
            }
            return super.visitClass(t, v);
        }

        @Override public Void visitMethod(MethodTree t, Void v) {
            TypeElement te = owner(getCurrentPath());
            String name = t.getName().contentEquals("<init>") ? "<init>" : t.getName().toString();
            ClassTree encl = (ClassTree) getCurrentPath().getParentPath().getLeaf();
            if (name.equals("<init>") && sp.getEndPosition(cu, t) < 0) return null; // implicit constructor
            boolean pushed = false;
            if (named(te) && sp.getStartPosition(cu, t) >= 0) {
                callers.push(te.getQualifiedName() + "#" + name);
                pushed = true;
            }
            try { return super.visitMethod(t, v); } finally { if (pushed) callers.pop(); }
        }

        String target(Element el) {
            if (!(el instanceof ExecutableElement ee)) return "";
            Element enc = ee.getEnclosingElement();
            if (!(enc instanceof TypeElement te)) return "";
            String q = te.getQualifiedName().toString();
            if (!repoTypes.contains(q)) return "";
            return q + "#" + (ee.getKind() == ElementKind.CONSTRUCTOR ? "<init>" : ee.getSimpleName());
        }

        void call(long pos, String name, Element el, String how) {
            if (pos < 0) return;
            String caller = callers.isEmpty() ? "" : callers.peek();
            row("call", "file", file, "line", "" + line(cu, pos), "caller", caller, "name", name,
                "target", target(el), "how", how);
        }

        String fold(ExpressionTree e) {
            if (e instanceof LiteralTree lt) return lt.getValue() instanceof String str ? str : null;
            if (e instanceof ParenthesizedTree pt) return fold(pt.getExpression());
            if (e instanceof BinaryTree bt && bt.getKind() == Tree.Kind.PLUS) {
                String a = fold(bt.getLeftOperand()), b = fold(bt.getRightOperand());
                return a == null || b == null ? null : a + b;
            }
            if (e instanceof IdentifierTree || e instanceof MemberSelectTree) {
                Element el = trees.getElement(new TreePath(getCurrentPath(), e));
                if (el instanceof VariableElement ve && ve.getConstantValue() instanceof String str) return str;
            }
            return null;
        }

        void config(MethodInvocationTree t, Element el, ExpressionTree sel) {
            if (!(el instanceof ExecutableElement ee) || !(ee.getEnclosingElement() instanceof TypeElement te)) return;
            String q = te.getQualifiedName().toString(), m = ee.getSimpleName().toString();
            int n = t.getArguments().size();
            boolean cfg = (q.equals("java.lang.System") && ((m.equals("getenv") && n == 1) || m.equals("getProperty")))
                || (q.equals("java.lang.Long") && m.equals("getLong"))
                || (q.equals("java.lang.Integer") && m.equals("getInteger"))
                || (q.equals("java.lang.Boolean") && m.equals("getBoolean"));
            if (!cfg && q.equals("java.util.Map") && (m.equals("getOrDefault") || m.equals("get")) && sel instanceof MemberSelectTree ms
                    && ms.getExpression() instanceof MethodInvocationTree inner
                    && inner.getMethodSelect() instanceof MemberSelectTree ims
                    && ims.getIdentifier().contentEquals("getenv") && inner.getArguments().isEmpty()) cfg = true;
            if (!cfg || n == 0) return;
            String key = fold(t.getArguments().get(0));
            long pos = sel instanceof MemberSelectTree ms2 ? sp.getEndPosition(cu, sel) - 1 : sp.getStartPosition(cu, sel);
            row("cfg", "file", file, "line", "" + line(cu, pos), "api", q + "#" + m, "key", key == null ? "" : key);
        }

        @Override public Void visitMethodInvocation(MethodInvocationTree t, Void v) {
            ExpressionTree sel = t.getMethodSelect();
            TreePath sp2 = new TreePath(getCurrentPath(), sel);
            Element el = trees.getElement(sp2);
            config(t, el, sel);
            String name;
            long pos;
            if (sel instanceof MemberSelectTree ms) {
                name = ms.getIdentifier().toString();
                pos = sp.getEndPosition(cu, sel) - 1;
            } else if (sel instanceof IdentifierTree id) {
                name = id.getName().toString();
                pos = sp.getStartPosition(cu, sel);
            } else { return super.visitMethodInvocation(t, v); }
            String how = name.equals("this") || name.equals("super") ? name : "invoke";
            call(pos, name, el, how);
            return super.visitMethodInvocation(t, v);
        }

        @Override public Void visitNewClass(NewClassTree t, Void v) {
            Element el = trees.getElement(getCurrentPath());
            call(sp.getStartPosition(cu, t), "<init>", el, "new");
            // an anonymous body is not a named class: keep scanning with the same caller
            return super.visitNewClass(t, v);
        }

        @Override public Void visitMemberReference(MemberReferenceTree t, Void v) {
            Element el = trees.getElement(getCurrentPath());
            String name = t.getName().toString();
            call(sp.getEndPosition(cu, t) - 1, name, el, "ref");
            return super.visitMemberReference(t, v);
        }
    }
}
