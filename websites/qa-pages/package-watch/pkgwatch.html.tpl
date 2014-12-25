<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <link rel="stylesheet" href="static/css/pure-min.css">
  <link rel="stylesheet" href="static/css/style.css">

  <link rel="shortcut icon" href="static/img/favicon.png">

  <title>Tanglu QA - Package Watch</title>
</head>
<body>
  {{extra_css}}
  <div class="tgl-g-r" id="layout">
    <a href="#menu" id="menuLink" class="menu-link">
      <span></span>
    </a>

    <div class="tgl-u" id="menu">
      <div class="pure-menu pure-menu-open">
        <a class="pure-menu-heading" href="/">Tanglu QA</a>

        <ul>
          <li class=" ">
            <a href="http://qa.tanglu.org">Overview</a>
          </li>

          <li class=" ">
            <a href="http://qa.tanglu.org/transitions/">Transition Tracker</a>
          </li>

          <li class=" ">
            <a href="http://qa.tanglu.org/staging-report/update_excuses.html">Staging Update Excuses</a>
          </li>

          <li class=" ">
            <a href="http://qa.tanglu.org/needs-build/">Missing Build-Dependencies</a>
          </li>

          <li class="pure-menu-selected">
            <a href="index.html">Package Watch</a>
          </li>

          <li class=" ">
            <a href="http://qa.tanglu.org/germinate/">Germinator</a>
          </li>

          <li class="menu-item-divided">
            <a href="http://ftp-master.tanglu.org">&#8611; FTP Masters</a>
          </li>

        </ul>
    </div>
  </div>

  <div class="pure-u-1" id="main">

  <div class="header">
    <img src="static/img/tanglu-devlogo.png" alt="Tanglu Development" />
    <h2>Tanglu developer resources.</h2>

  </div>

  <div class="content">
    {{content}}
  </div>


  <div class="legal pure-g-r">
    <div class="pure-u-2-5">
        <div class="l-box">
            <p class="legal-license">
                This site is built using Pure v0.3<br>
            </p>
        </div>
    </div>

    <div class="pure-u-1-5">
        <div class="l-box legal-logo">
            <a href="http://tanglu.org/">
                <img src="static/img/tanglu-small-mono.png" alt="Tanglu logo">
            </a>
        </div>
    </div>

    <div class="pure-u-2-5">
        {{extra_footer}}
        <p class="legal-copyright">
            &copy; 2014 Tanglu Project
        </p>
    </div>
  </div>

    </div>
  </div>
</body>
</html>
