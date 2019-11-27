from krun.util import print_stderr_linewise

def test_quadratic():
    l = []
    pr = print_stderr_linewise(l.append)
    pr.next() # start it
    for i in range(100):
        pr.send("abc")
    pr.send("\n" * 1000000)

def test_print_stderr_linewise():
    l = []
    pr = print_stderr_linewise(l.append)
    pr.next() # start it
    pr.send("abc")
    assert l == []
    pr.send("def")
    assert l == []
    pr.send("\n")
    assert l == ["stderr: abcdef"]
    pr.send("ab\nde\nfg")
    assert l == ["stderr: abcdef", "stderr: ab", "stderr: de"]
    pr.send("\n")
    assert l == ["stderr: abcdef", "stderr: ab", "stderr: de", "stderr: fg"]
