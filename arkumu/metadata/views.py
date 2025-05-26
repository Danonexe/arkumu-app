from django.shortcuts import render

def daisy_test(request):
    """
    A simple view to render the daisyUI test page.
    """
    return render(request, 'metadata/daisy_test.html')

