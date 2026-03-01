This part is the frontend of the app.
It will use React technology to display a modern ergonomic interface, rendering a good UI/UX.
Design will be modern and simple. A bit a nerdy one.

Pages :
- home : portfolio sythesis display
  - display a graph of the overall portfolio value evolution (for the last 6 months for example);
  - todays p&l
  - pie chart of the share (%) of each asset in the portfolio
  - list the overall portfolio positions (ranked by folio share)
- performance : in depth performance display
  - access : this page is displayed when clicking on 'more' on the synthesis value evo graph
  - folio value evolution graph display (since the beginning)
  - display of daily p&l value
  - feature to compare folio performance to BTC performance, visually on the graph + compare daily p&l
- position : in deph position analysis
  - access : when clicking on one position of the portfolio
  - on the top right, display : value and token quantity bought, current p&l and position duration
  - display a main graph price (trading view like) with a display of all the buying and selling orders executed
  - on a left side bar, list all the executed orders : time, value, quantity bought
  - (v2) : tag an order as a position open/close to compute mean entry price perf and not compute with overall
- (v2) position tagging : feature of tagging positions to distinguish positions who are vc plays, classic folio or more trading etc
  - (v2) display performances according to each tag defined for better per folio analysis
